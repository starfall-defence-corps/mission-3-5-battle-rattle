"""
Phase 2 — Collect the Evidence
==============================
Before you can respond you must know WHAT you are responding to. Author a
read-only runbooks/collect-triage.yml that reads the incident log at
`-e evidence_log=<path>`, finds the attacker's indicator IP (the source that
appears most), and writes a machine-readable report at `-e report_path=<path>`
ON EACH NODE:

    {"indicator_ip": "<the top source IP>", "hits": <count on THIS node>}

ARIA runs it against two independent incidents. It must discover the real
indicator each time (never a memorised one) and count per node — and it must
not change anything on the box (recon is read-only).
"""
import json
import os

import pytest

from conftest import (
    FLEET, dual_nonce, load_baseline, node_run, run_playbook,
)


def _runbook():
    return os.path.join(os.path.dirname(__file__), "..", "..", "..",
                        "workspace", "runbooks", "collect-triage.yml")


def _canary_hashes(host, paths):
    """sha256 of a set of files on a node — for the read-only guarantee."""
    out = {}
    for p in paths:
        r = node_run(host, f"sha256sum {p} 2>/dev/null | cut -d' ' -f1")
        out[p] = r.stdout.strip()
    return out


class TestPhase2CollectTriage:

    def test_triage_runbook_present(self):
        p = _runbook()
        assert os.path.isfile(p) and os.path.getsize(p) > 0, (
            "ARIA: No runbooks/collect-triage.yml. Author a read-only playbook that "
            "extracts the top indicator from -e evidence_log and writes a JSON report "
            "to -e report_path on each node."
        )

    def test_triage_report_both(self):
        b = load_baseline()
        if b is None:
            pytest.skip("baseline missing — run 'make setup'")
        cfg = b["verbs"]["collect_triage"]

        # Read-only canary: nothing outside the report may change.
        canary_paths = ["/etc/passwd", "/etc/sdc/canary",
                        cfg["scenario_a"]["evars"]["evidence_log"],
                        cfg["scenario_b"]["evars"]["evidence_log"]]
        canary = {h: _canary_hashes(h, canary_paths) for h in FLEET}

        def invoke(sc):
            return run_playbook("collect-triage", sc["evars"])

        def precondition(sc, host):
            log = sc["evars"]["evidence_log"]
            r = node_run(host, f"test -f {log} && echo ok")
            assert r.stdout.strip() == "ok", f"evidence log {log} absent"

        def _report(sc, host):
            rp = sc["evars"]["report_path"]
            r = node_run(host, f"cat {rp} 2>/dev/null")
            return r.stdout.strip()

        def probe(sc, host):
            raw = _report(sc, host)
            assert raw, (
                f"ARIA: No triage report at {sc['evars']['report_path']} on {host}. "
                f"Write the JSON report on every node, not just the control host."
            )
            try:
                doc = json.loads(raw)
            except ValueError:
                pytest.fail(
                    f"ARIA: The triage report on {host} is not valid JSON. Emit "
                    f'{{"indicator_ip": "...", "hits": N}} — use to_nice_json / a template.'
                )
            assert doc.get("indicator_ip") == sc["indicator_ip"], (
                f"ARIA: Your report on {host} names '{doc.get('indicator_ip')}', but the "
                f"incident's top indicator is different. Discover it from the log — do not "
                f"hardcode an address."
            )
            assert int(doc.get("hits", -1)) == sc["hits"][host], (
                f"ARIA: The hit count on {host} ({doc.get('hits')}) does not match the "
                f"evidence ({sc['hits'][host]}). Count the indicator's lines on THIS node."
            )

        def liveness(sc, host):
            now = _canary_hashes(host, canary_paths)
            assert now == canary[host], (
                f"ARIA: collect-triage changed something on {host} — recon must be "
                f"read-only. Gather and report; do not modify the host."
            )

        def fingerprint(sc, host):
            return _report(sc, host)

        dual_nonce(
            "collect-triage", cfg["scenario_a"], cfg["scenario_b"],
            invoke=invoke, probe=probe, liveness=liveness,
            idempotence="fingerprint", fingerprint=fingerprint,
            precondition=precondition,
        )
