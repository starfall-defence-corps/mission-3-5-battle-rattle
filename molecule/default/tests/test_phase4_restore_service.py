"""
Phase 4 — Restore the Service  (the capstone)
=============================================
The Hydra downed a scored service on every node — one by corrupting its unit,
one by deleting it. A restart cannot fix either. Author a declarative
runbooks/restore-service.yml that reconciles `-e service_name=<svc>` back to the
known-good state kept at `-e golden_root=<dir>`:

    copy {{ golden_root }}/{{ service_name }}.service  ->  /etc/systemd/system/
    (notify a daemon-reload handler)  ->  enable + start the service

ARIA breaks two different services two different ways, then runs YOUR runbook
against each. Both must come back — active, enabled, and serving their correct
content — on every node, idempotently. A bare `systemctl restart` fixes neither;
a hardcoded service name fixes only one.
"""
import os

import pytest

from conftest import (
    FLEET, dual_nonce, load_baseline, node_run, run_playbook, ssh_port_answers,
)


def _runbook():
    return os.path.join(os.path.dirname(__file__), "..", "..", "..",
                        "workspace", "runbooks", "restore-service.yml")


def _is_active(host, svc):
    return node_run(host, f"systemctl is-active {svc}").stdout.strip() == "active"


def _is_enabled(host, svc):
    return node_run(host, f"systemctl is-enabled {svc} 2>/dev/null").stdout.strip() == "enabled"


def _served_token(host, port):
    r = node_run(host, f"curl -s --max-time 3 http://localhost:{port}")
    return r.stdout.strip()


def _break_services(cfg):
    """Down both scored services on every node, two different ways, so a real
    declarative reconcile (not a restart) is required to bring them back."""
    a = cfg["scenario_a"]["evars"]["service_name"]
    b = cfg["scenario_b"]["evars"]["service_name"]
    for host in FLEET:
        # A: corrupt the installed unit in place
        node_run(host, f"systemctl stop {a}; systemctl disable {a} 2>/dev/null; "
                       f"echo 'CORRUPTED BY THE HYDRA' > /etc/systemd/system/{a}.service")
        # B: delete the installed unit entirely
        node_run(host, f"systemctl stop {b}; rm -f /etc/systemd/system/{b}.service")
        node_run(host, "systemctl daemon-reload")


class TestPhase4RestoreService:

    def test_restore_runbook_present(self):
        p = _runbook()
        assert os.path.isfile(p) and os.path.getsize(p) > 0, (
            "ARIA: No runbooks/restore-service.yml. Author a declarative playbook that "
            "restores -e service_name from the known-good store at -e golden_root."
        )

    def test_service_restored_both(self):
        b = load_baseline()
        if b is None:
            pytest.skip("baseline missing — run 'make setup'")
        cfg = b["verbs"]["restore_service"]

        _break_services(cfg)   # arm the outage right before the phase

        def invoke(sc):
            return run_playbook("restore-service", sc["evars"])

        def precondition(sc, host):
            svc = sc["evars"]["service_name"]
            assert not _is_active(host, svc), f"service {svc} is not down on {host}"

        def probe(sc, host):
            svc = sc["evars"]["service_name"]
            assert _is_active(host, svc), (
                f"ARIA: {svc} is not active on {host} after restore-service. Reconcile the "
                f"unit from {sc['evars']['golden_root']} and start it — a restart cannot "
                f"revive a corrupted or missing unit."
            )
            assert _is_enabled(host, svc), (
                f"ARIA: {svc} is not enabled on {host} — it will not survive a reboot. "
                f"Enable it as part of the restore."
            )
            token = _served_token(host, sc["port"])
            assert token == sc["token"], (
                f"ARIA: {svc} on {host} is not serving its known-good content "
                f"(got '{token}'). Restore from the golden store, don't improvise a listener."
            )

        def liveness(sc, host):
            assert ssh_port_answers(host), f"ARIA: {host} stopped answering SSH."

        def disjoint(sc_a, sc_b, host):
            for sc in (sc_a, sc_b):
                svc = sc["evars"]["service_name"]
                assert _is_active(host, svc) and _served_token(host, sc["port"]) == sc["token"], (
                    f"ARIA: Restoring one service disturbed the other on {host}. Act only on "
                    f"service_name — {svc} must keep serving its own content."
                )

        dual_nonce(
            "restore-service", cfg["scenario_a"], cfg["scenario_b"],
            invoke=invoke, probe=probe, liveness=liveness,
            idempotence="changed", precondition=precondition, disjoint=disjoint,
        )
