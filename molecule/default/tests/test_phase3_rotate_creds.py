"""
Phase 3 — Rotate the Credential
===============================
A service account has been compromised on every node. Author a PARAMETERISED
runbooks/rotate-creds.yml that sets a new password for `-e target_user=<user>`
to `-e new_password=<secret>`, fleet-wide — leaving the account usable.

ARIA runs it against two different compromised users. Each one's old password
must stop working and the new one must work, on every node — and re-running the
runbook must NOT churn the credential (a stable hash, not a fresh salt each time).
Hardcode the username and the second account stays compromised.
"""
import os

import pytest

from conftest import (
    FLEET, dual_nonce, load_baseline, node_run, run_playbook, ssh_port_answers,
)


def _runbook():
    return os.path.join(os.path.dirname(__file__), "..", "..", "..",
                        "workspace", "runbooks", "rotate-creds.yml")


def _stored_hash(host, user):
    r = node_run(host, f"getent shadow {user} | cut -d: -f2")
    return r.stdout.strip()


def _password_matches(host, user, password):
    """True iff `password` is the account's current password (verified on the
    node via crypt against the stored $6$ hash — Linux-side, so it works
    regardless of the cadet's host OS)."""
    # Verify against the stored hash with crypt on the node. Accept ANY real
    # crypt algorithm ($6$ sha512, $y$ yescrypt — the Ubuntu 22.04 chpasswd
    # default, etc.); reject a locked/absent hash. Correctness is the crypt
    # match, not the algorithm.
    script = (
        "import crypt,subprocess,sys\n"
        f"h=subprocess.check_output(['getent','shadow','{user}']).decode().split(':')[1]\n"
        f"ok = bool(h) and h[0]=='$' and crypt.crypt({password!r}, h)==h\n"
        "sys.exit(0 if ok else 1)\n"
    )
    r = node_run(host, "python3 -c " + _shq(script))
    return r.returncode == 0


def _shq(s):
    """Single-quote a string for a bash -lc argument."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


class TestPhase3RotateCreds:

    def test_rotate_runbook_present(self):
        p = _runbook()
        assert os.path.isfile(p) and os.path.getsize(p) > 0, (
            "ARIA: No runbooks/rotate-creds.yml. Author a parameterised playbook that "
            "rotates -e target_user to -e new_password fleet-wide."
        )

    def test_creds_rotated_both(self):
        b = load_baseline()
        if b is None:
            pytest.skip("baseline missing — run 'make setup'")
        cfg = b["verbs"]["rotate_creds"]

        def invoke(sc):
            return run_playbook("rotate-creds", sc["evars"])

        def precondition(sc, host):
            user = sc["evars"]["target_user"]
            assert _password_matches(host, user, sc["old_password"]), (
                f"compromised user {user} does not have its known old password on {host}"
            )

        def probe(sc, host):
            user = sc["evars"]["target_user"]
            new = sc["evars"]["new_password"]
            assert _password_matches(host, user, new), (
                f"ARIA: {user}'s new password does not work on {host} after rotate-creds. "
                f"Set target_user's password to new_password on every node."
            )
            assert not _password_matches(host, user, sc["old_password"]), (
                f"ARIA: {user}'s OLD password still works on {host}. The compromised "
                f"credential must be revoked, not left alongside the new one."
            )

        def liveness(sc, host):
            user = sc["evars"]["target_user"]
            r = node_run(host, f"passwd -S {user} | awk '{{print $2}}'")
            assert r.stdout.strip() == "P", (
                f"ARIA: {user} is not in a usable password state on {host} "
                f"(passwd -S = '{r.stdout.strip()}'). Rotate the credential — do not lock "
                f"or disable the account."
            )
            assert ssh_port_answers(host), f"ARIA: {host} stopped answering SSH."

        def fingerprint(sc, host):
            return _stored_hash(host, sc["evars"]["target_user"])

        dual_nonce(
            "rotate-creds", cfg["scenario_a"], cfg["scenario_b"],
            invoke=invoke, probe=probe, liveness=liveness,
            idempotence="fingerprint", fingerprint=fingerprint,
            precondition=precondition,
        )
