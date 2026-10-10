"""network/tc-hook-order: who attaches where on the ports, and who owns which mark bits.

The emulator tests run with dae on, so all three components hold their hooks:
einat on tcx and qosify's legacy filters on pppoe-wan, dae alone on br-lan.
"""

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from wrt_tests import spec
from wrt_tests.model.poll import until
from wrt_tests.sandbox.net import DIRECT_TARGET
from wrt_tests.sandbox.netprobe import BIG
from wrt_tests.services.datapath import DAE, EINAT, QOSIFY, hooks

if TYPE_CHECKING:
    from wrt_tests.device.router import Router
    from wrt_tests.services.datapath import Online

CAPABILITY = "network/tc-hook-order"
MARKS_CHECK = Path(__file__).resolve().parents[2] / "scripts" / "marks-check.sh"
# The bit dae keeps for its own sockets (config/marks.tsv).
DAE_BIT = "0x00000100"
# qosify's classifier on both directions, and its four u32 filters that send DNS
# replies (source port 53, TCP and UDP, IPv4 and IPv6) to ifb-dns.
DNS_REDIRECTS = 4
WAN = {**EINAT, **QOSIFY}
SETTLE = 60


def _ports(router: Router) -> tuple[dict[str, list[str]], int, dict[str, list[str]]]:
    """Return what sits on the ports: pppoe-wan's programs and DNS redirects, br-lan's programs."""
    redirects = router.run("tc filter show dev pppoe-wan ingress").count("ifb-dns")
    return hooks(router, "pppoe-wan"), redirects, hooks(router, "br-lan")


def _in_order(router: Router) -> bool:
    return _ports(router) == (WAN, DNS_REDIRECTS, DAE)


def _qosify_runs(router: Router, direction: str) -> int:
    """Return how often qosify's classifier on ``direction`` of pppoe-wan has run.

    qosify's own counters (ubus get_stats) add up both directions, so this reads
    the run count of the program instance on the hook (kernel.bpf_stats_enabled).
    """
    shown = router.run("bpftool net show dev pppoe-wan").splitlines()
    (program,) = [line.split()[-1] for line in shown if f"clsact/{direction}" in line]
    return int(json.loads(router.run(f"bpftool -j prog show id {program}")).get("run_cnt", 0))


@spec(CAPABILITY, "Programs and order on the WAN port", "Check the WAN port")
def test_wan_port_runs_einat_then_qosify(dae: Online) -> None:
    programs, redirects, _ = _ports(dae.router)
    assert programs == WAN
    assert redirects == DNS_REDIRECTS


@spec(CAPABILITY, "Only dae on the LAN port", "Check the LAN port")
def test_lan_port_runs_only_dae(dae: Online) -> None:
    assert hooks(dae.router, "br-lan") == DAE


@spec(CAPABILITY, "Pass-through returns continue the chain", "ICMP reply on WAN ingress")
def test_icmp_reply_reaches_qosify_and_the_host(dae: Online) -> None:
    router = dae.router
    router.run("sysctl -qw kernel.bpf_stats_enabled=1")
    try:
        before = _qosify_runs(router, "ingress")
        dae.client().run("ping", "-c", "3", "-W", "2", DIRECT_TARGET[0])
        assert _qosify_runs(router, "ingress") >= before + 3
    finally:
        router.run("sysctl -qw kernel.bpf_stats_enabled=0")


@spec(CAPABILITY, "Pass-through returns continue the chain", "Fragmented UDP reply")
def test_fragmented_reply_arrives_whole(dae: Online) -> None:
    seen = dae.client().probe("udp", DIRECT_TARGET[0], "--big")
    assert seen["size"] == BIG
    assert seen["address"] == dae.wan_address


@spec(CAPABILITY, "Order independent of startup order", "After restarting components")
def test_order_survives_restarts_and_a_redial(dae: Online) -> None:
    for step in ("qosify", "einat", "dae"):
        dae.router.run(f"/etc/init.d/{step} restart")
        until(
            lambda: _in_order(dae.router), timeout=SETTLE, what=f"the order after restarting {step}"
        )
    dae.redial()
    until(lambda: _in_order(dae.router), timeout=SETTLE, what="the order after a redial")


@spec(CAPABILITY, "Centralized mark bit allocation", "Overlapping mark configured")
def test_overlapping_mark_is_reported(tmp_path: Path) -> None:
    template = tmp_path / "feed" / "net" / "demo" / "files" / "uci-config"
    template.parent.mkdir(parents=True)
    template.write_text(f"config demo 'config'\n\toption mark '{DAE_BIT}'\n")
    result = subprocess.run(
        [MARKS_CHECK, tmp_path / "feed"], capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert f"mark {DAE_BIT} (demo) overlaps {DAE_BIT} (dae)" in result.stderr

    template.write_text("config demo 'config'\n")
    result = subprocess.run(
        [MARKS_CHECK, tmp_path / "feed"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
