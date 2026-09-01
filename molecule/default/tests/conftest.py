"""
ARIA verification harness — MOS 5: Battle Rattle
================================================

Grades REUSABILITY, not one lucky incident. For each of the four IR verbs the
range arms TWO independent, randomised scenarios (A/B). The grader runs the
cadet's SAME runbook (workspace/runbooks/<verb>.yml) against BOTH, in one lab
pass. A runbook hardcoded to scenario A passes A and FAILS B — proving it is a
battle rattle (works for ANY indicator), not a memorised one-off.

Design principles (shared with the 2.5 / 3.4 range harnesses):
  - Ground truth is the gitignored `.lab/baseline.json` (per-run nonce indicators,
    users, services, evidence), written at `make setup`.
  - Effects are probed INDEPENDENT of the cadet's implementation: firewall drops
    are tested by sourcing traffic from the range; credential/service/report state
    is read straight off the node via `docker exec`.
  - All-nodes: a scenario passes only if EVERY fleet node satisfies it. No partial
    credit.
  - Every verb is graded for idempotence — a second identical run must not churn
    state (that is what makes a runbook safe to re-run mid-incident).
  - A dead lab / broken plant reads as SKIP or an explicit INCONCLUSIVE failure,
    never a false pass. `require_lab_alive()` is the single chokepoint for that.

The one primitive — `dual_nonce(...)` — is written once here; each verb's phase
test supplies a plant-independent probe/liveness and calls it.
"""
import json
import os
import subprocess

import pytest

# -- fleet topology ----------------------------------------------------------
FLEET = ["sdc-web", "sdc-db", "sdc-comms"]
NODE_IP = {"sdc-web": "172.30.0.11", "sdc-db": "172.30.0.12", "sdc-comms": "172.30.0.13"}
SSH_PORT = {"sdc-web": 2221, "sdc-db": 2222, "sdc-comms": 2223}
RANGE = "sdc-range"


# -- paths -------------------------------------------------------------------
def _root_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


def _workspace_dir():
    return os.path.join(_root_dir(), "workspace")


def _lab_dir():
    return os.path.join(_root_dir(), ".lab")


def _capped(timeout):
    """Optional ceiling on any wait (seconds). Unset in normal use; the
    range-build harness sets ARIA_MAX_WAIT to iterate quickly."""
    override = os.environ.get("ARIA_MAX_WAIT")
    if override:
        try:
            return min(timeout, int(override))
        except ValueError:
            pass
    return timeout


# -- baseline (grader ground truth) ------------------------------------------
def load_baseline():
    try:
        with open(os.path.join(_lab_dir(), "baseline.json")) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return None


# ===========================================================================
#  Lab liveness — the ONLY place the "never a false pass" invariant lives.
# ===========================================================================
def _inconclusive(msg):
    pytest.fail(
        "ARIA: " + msg + " This result is INCONCLUSIVE, not a pass or a fail. "
        "Run 'make reset' to re-arm the range, then 'make test' again."
    )


def _container_running(name):
    r = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        capture_output=True, text=True, timeout=15,
    )
    return r.returncode == 0 and r.stdout.strip() == "true"


def require_lab_alive():
    """Structural breach (no baseline) -> INCONCLUSIVE fail. Lab simply offline
    -> SKIP. Either way, never a pass on an unarmed range."""
    b = load_baseline()
    if b is None:
        pytest.skip("range baseline missing — run 'make setup' first")
    if not _container_running(RANGE) or not all(_container_running(n) for n in FLEET):
        pytest.skip("lab containers not all running — run 'make reset'")
    return b


# ===========================================================================
#  Running the cadet's runbook (ansible JSON callback -> RunResult)
# ===========================================================================
class RunResult:
    def __init__(self, rc, changed, failed, unreachable, hosts, raw):
        self.rc = rc
        self.changed = changed            # {host: int}
        self.failed = failed              # {host: int}
        self.unreachable = unreachable    # {host: int}
        self.hosts = hosts                # set of hosts that actually ran
        self.raw = raw


def _extract_json(text):
    """Pull the ansible json-callback document out of stdout, tolerating leading
    warnings and trailing noise. Scans each '{' with raw_decode and returns the
    first object that looks like the callback output (has 'stats' or 'plays')."""
    dec = json.JSONDecoder()
    idx = 0
    while True:
        i = text.find("{", idx)
        if i == -1:
            return None
        try:
            obj, _ = dec.raw_decode(text[i:])
            if isinstance(obj, dict) and ("stats" in obj or "plays" in obj):
                return obj
        except ValueError:
            pass
        idx = i + 1


def run_playbook(verb, evars, timeout=180):
    """Run workspace/runbooks/<verb>.yml with -e <evars-json> and return a
    RunResult. Uses the workspace ansible.cfg + inventory + key."""
    ws = _workspace_dir()
    env = dict(os.environ)
    env["ANSIBLE_CONFIG"] = os.path.join(ws, "ansible.cfg")
    env["ANSIBLE_STDOUT_CALLBACK"] = "json"
    env["ANSIBLE_DEPRECATION_WARNINGS"] = "False"
    env["ANSIBLE_LOCALHOST_WARNING"] = "False"
    playbook = os.path.join("runbooks", verb + ".yml")
    proc = subprocess.run(
        ["ansible-playbook", playbook, "-e", json.dumps(evars)],
        capture_output=True, text=True, timeout=_capped(timeout), cwd=ws, env=env,
    )
    changed, failed, unreachable = {}, {}, {}
    doc = _extract_json(proc.stdout)   # parse stdout ONLY (stderr may hold noise)
    stats = (doc or {}).get("stats", {})
    for h in FLEET:
        s = stats.get(h, {})
        changed[h] = int(s.get("changed", 0))
        failed[h] = int(s.get("failures", 0))
        unreachable[h] = int(s.get("unreachable", 0))
    hosts = set(stats.keys())
    return RunResult(proc.returncode, changed, failed, unreachable, hosts,
                     (proc.stdout or "") + (proc.stderr or ""))


def assert_run_ok(verb, sc_label, r):
    assert r.rc == 0, (
        f"ARIA: Your {verb}.yml exited non-zero on scenario {sc_label}.\n"
        f"{r.raw[-600:]}"
    )
    missing = [h for h in FLEET if h not in r.hosts]
    assert not missing, (
        f"ARIA: {verb}.yml did not run on every fleet node ({', '.join(missing)} "
        f"missing from the play). Target the whole `fleet` group, not one host."
    )
    for h in FLEET:
        assert r.failed[h] == 0 and r.unreachable[h] == 0, (
            f"ARIA: {verb}.yml had a failed/unreachable task on {h} (scenario "
            f"{sc_label}). Every node must complete cleanly."
        )


# ===========================================================================
#  Probe primitives (implementation-independent effect checks)
# ===========================================================================
def node_run(node, cmd, timeout=25):
    """Run a shell command inside a fleet node (as root)."""
    return subprocess.run(
        ["docker", "exec", node, "bash", "-lc", cmd],
        capture_output=True, text=True, timeout=_capped(timeout),
    )


def range_can_reach(dst_ip, port, src_ip=None, timeout=3):
    """From the range container, attempt a TCP connect to dst:port, optionally
    sourced from a specific (attacker) IP. True iff the connection establishes."""
    src = src_ip or ""
    script = (
        "import socket,sys\n"
        f"s=socket.socket(); s.settimeout({timeout})\n"
        f"src='{src}'\n"
        "try:\n"
        "    if src: s.bind((src,0))\n"
        f"    s.connect(('{dst_ip}',{port})); s.close(); sys.exit(0)\n"
        "except Exception: sys.exit(1)\n"
    )
    r = subprocess.run(
        ["docker", "exec", RANGE, "python3", "-c", script],
        capture_output=True, text=True, timeout=_capped(timeout + 5),
    )
    return r.returncode == 0


def ssh_port_answers(node, timeout=3):
    """The node's SSH is reachable on its published host port (grader liveness)."""
    import socket
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect(("localhost", SSH_PORT[node])); s.close()
        return True
    except OSError:
        return False


# ===========================================================================
#  THE PRIMITIVE — dual-nonce reusability contract (written once)
# ===========================================================================
def dual_nonce(verb, scenario_a, scenario_b, *, invoke, probe, liveness,
               idempotence="changed", fingerprint=None,
               precondition=None, disjoint=None):
    """Run the SAME cadet runbook against TWO disjoint nonce scenarios, in one
    lab pass, enforcing the platform invariants:

      * all-nodes (probe + liveness on EVERY fleet node)
      * dead lab / broken plant -> INCONCLUSIVE (never a false pass)
      * idempotence ("changed": 0 changes on re-run, or "fingerprint": state
        byte-identical on re-run)
      * A hardcoded solution passes one scenario and fails the other.

    invoke(sc)          -> RunResult   (runs runbooks/<verb>.yml -e sc["evars"])
    probe(sc, host)     -> None        (asserts the effect landed; impl-independent)
    liveness(sc, host)  -> None        (asserts the box is still healthy)
    precondition(sc, h) -> None/raises (asserts the plant is live BEFORE run 1)
    disjoint(a, b, h)   -> None        (asserts A and B did not clobber each other)
    """
    require_lab_alive()
    for label, sc in (("A", scenario_a), ("B", scenario_b)):
        if precondition:
            for h in FLEET:
                try:
                    precondition(sc, h)
                except AssertionError as e:
                    _inconclusive(f"{verb} scenario {label} plant is not live on {h}: {e}")

        r1 = invoke(sc)
        assert_run_ok(verb, label, r1)
        fp1 = {h: fingerprint(sc, h) for h in FLEET} if fingerprint else None

        for h in FLEET:
            probe(sc, h)
            liveness(sc, h)

        r2 = invoke(sc)   # idempotence run
        assert_run_ok(verb, label, r2)
        if idempotence == "changed":
            for h in FLEET:
                assert r2.changed[h] == 0, (
                    f"ARIA: {verb}.yml is not idempotent on {h} (scenario {label}): "
                    f"re-running it reported {r2.changed[h]} change(s). A response you "
                    f"cannot safely re-run mid-incident is a liability — make it converge."
                )
        elif idempotence == "fingerprint":
            for h in FLEET:
                assert fingerprint(sc, h) == fp1[h], (
                    f"ARIA: {verb}.yml churned state on {h} (scenario {label}) when "
                    f"re-run — the result changed on an identical second run. Make it "
                    f"deterministic and idempotent."
                )

        for h in FLEET:      # effect + liveness still hold after the second run
            probe(sc, h)
            liveness(sc, h)

    if disjoint:
        for h in FLEET:
            disjoint(scenario_a, scenario_b, h)


# ===========================================================================
#  ARIA reporter (presentation only)
# ===========================================================================
from aria_reporter import configure  # noqa: E402

configure(
    mission_id="3-5",
    phases={
        "TestPhase1BlockIOC":       ("1", "Block the Indicator"),
        "TestPhase2CollectTriage":  ("2", "Collect the Evidence"),
        "TestPhase3RotateCreds":    ("3", "Rotate the Credential"),
        "TestPhase4RestoreService": ("4", "Restore the Service"),
    },
    friendly={
        "test_block_runbook_present":   "block-ioc.yml present at runbooks/",
        "test_ioc_blocked_both":        "Both indicators blocked fleet-wide (any IOC)",
        "test_triage_runbook_present":  "collect-triage.yml present at runbooks/",
        "test_triage_report_both":      "Both indicators found + counted on every node",
        "test_rotate_runbook_present":  "rotate-creds.yml present at runbooks/",
        "test_creds_rotated_both":      "Both credentials rotated fleet-wide (any user)",
        "test_restore_runbook_present": "restore-service.yml present at runbooks/",
        "test_service_restored_both":   "Both services restored from known-good (any service)",
    },
)
