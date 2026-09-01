"""
Phase 1 — Block the Indicator
=============================
The Hydra is hammering the fleet from an attacker IP. Author a PARAMETERISED
runbooks/block-ioc.yml that firewall-DROPs all traffic from a given indicator,
fleet-wide, accepting the address via `-e ioc_ip=<ip>`.

ARIA runs your runbook against TWO different attacker IPs (you can see neither).
Both must go dark on every node — while a legitimate source still gets through.
Hardcode one address and you seal it but the second attacker walks straight in.
"""
import os

from conftest import (
    NODE_IP, dual_nonce, load_baseline, range_can_reach, run_playbook,
    ssh_port_answers,
)


def _runbook():
    return os.path.join(os.path.dirname(__file__), "..", "..", "..",
                        "workspace", "runbooks", "block-ioc.yml")


class TestPhase1BlockIOC:

    def test_block_runbook_present(self):
        p = _runbook()
        assert os.path.isfile(p) and os.path.getsize(p) > 0, (
            "ARIA: No runbooks/block-ioc.yml. Author a parameterised playbook that "
            "firewall-drops a given IOC fleet-wide, taking the address via -e ioc_ip=<ip>."
        )

    def test_ioc_blocked_both(self):
        b = load_baseline()
        if b is None:
            import pytest
            pytest.skip("baseline missing — run 'make setup'")
        cfg = b["verbs"]["block_ioc"]
        port = cfg["probe_port"]
        control = cfg["control_ip"]

        def invoke(sc):
            return run_playbook("block-ioc", sc["evars"])

        def precondition(sc, host):
            ioc = sc["evars"]["ioc_ip"]
            assert range_can_reach(NODE_IP[host], port, src_ip=ioc), (
                f"attacker {ioc} cannot reach {host} even before the block"
            )

        def probe(sc, host):
            ioc = sc["evars"]["ioc_ip"]
            assert not range_can_reach(NODE_IP[host], port, src_ip=ioc), (
                f"ARIA: {ioc} still reaches {host} after your block-ioc ran. Drop ALL "
                f"traffic from ioc_ip on every node (ansible.builtin.iptables, "
                f"source={{{{ ioc_ip }}}}, jump: DROP)."
            )

        def liveness(sc, host):
            assert range_can_reach(NODE_IP[host], port, src_ip=control), (
                f"ARIA: A legitimate source ({control}) can no longer reach {host}. Your "
                f"block must drop the ONE indicator, not everyone — no blanket -P INPUT DROP."
            )
            assert ssh_port_answers(host), (
                f"ARIA: {host} stopped answering SSH after your block. You locked out the fleet."
            )

        def disjoint(a, b_, host):
            for sc in (a, b_):
                ioc = sc["evars"]["ioc_ip"]
                assert not range_can_reach(NODE_IP[host], port, src_ip=ioc), (
                    f"ARIA: Blocking one indicator un-blocked another on {host}. Each run "
                    f"must add its own drop without removing the others'."
                )

        dual_nonce(
            "block-ioc", cfg["scenario_a"], cfg["scenario_b"],
            invoke=invoke, probe=probe, liveness=liveness,
            idempotence="changed", precondition=precondition, disjoint=disjoint,
        )
