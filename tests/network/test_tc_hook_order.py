"""network/tc-hook-order: who attaches where on the ports, and who owns which mark bits.

The emulator tests run with dae on, so all three components hold their hooks:
einat and then qosify on tcx on pppoe-wan, dae alone on br-lan.
"""

import json
import re
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.model.poll import until
from wrt_tests.sandbox.net import DIRECT_TARGET
from wrt_tests.sandbox.netprobe import BIG
from wrt_tests.services import qos
from wrt_tests.services.datapath import DAE, EINAT, QOSIFY_CLSACT, WAN, hooks, tc_programs

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.device.router import Router
    from wrt_tests.services.datapath import Online

CAPABILITY = "network/tc-hook-order"
MARKS_CHECK = Path(__file__).resolve().parents[2] / "scripts" / "marks-check.sh"
# The bit dae keeps for its own sockets (config/marks.tsv).
DAE_BIT = "0x00000100"
# pppoe-wan when qosify falls back to clsact: einat on tcx, qosify's filters after.
FALLBACK = {**EINAT, **QOSIFY_CLSACT}
SETTLE = 60
# The ICMP test's pings: so many in so short a time that their replies stand out
# from the WAN's background traffic, a few packets a second, which a quiet
# window as long shows (test-fidelity D4).
PINGS = 200
PING_INTERVAL = 0.01


def _filters(router: Router) -> str:
    """Return the legacy tc filters on pppoe-wan, of both directions."""
    shown = "tc filter show dev pppoe-wan ingress; tc filter show dev pppoe-wan egress"
    return router.run(shown).strip()


def _in_order(router: Router) -> bool:
    return (hooks(router, "pppoe-wan"), _filters(router), hooks(router, "br-lan")) == (
        WAN,
        "",
        DAE,
    )


def _set_tcx(router: Router, value: str) -> None:
    """Set (or, given "", delete) qosify's defaults option tcx, and reload qosify."""
    option = "qosify.@defaults[0].tcx"
    change = f"uci set {option}={value}" if value else f"uci -q delete {option}"
    router.run(f"{change} ; uci commit qosify && /etc/init.d/qosify reload")


def _qosify_runs(router: Router, direction: str) -> int:
    """Return how often qosify's classifier on ``direction`` of pppoe-wan has run.

    qosify's own counters (ubus get_stats) add up both directions, so this reads
    the run count of the program instance on the hook (kernel.bpf_stats_enabled).
    """
    (program,) = [
        found["prog_id"]
        for found in tc_programs(router, "pppoe-wan")
        if (found["kind"], found["name"]) == (f"tcx/{direction}", "qosify_classify")
    ]
    return int(json.loads(router.run(f"bpftool -j prog show id {program}")).get("run_cnt", 0))


@pytest.fixture
def without_tcx(dae: Online, internet_zone: Online) -> Iterator[Online]:
    """Have qosify attach with clsact, as on a kernel without tcx, for the test."""
    del internet_zone  # the names a dns: rule sends to a class resolve to the LAN
    router = dae.router
    _set_tcx(router, "0")
    try:
        until(
            lambda: hooks(router, "pppoe-wan") == FALLBACK, timeout=SETTLE, what="qosify on clsact"
        )
        yield dae
    finally:
        _set_tcx(router, "")
        until(lambda: _in_order(router), timeout=SETTLE, what="qosify on tcx again")


@spec(CAPABILITY, "Programs and order on the WAN port", "Check the WAN port")
def test_wan_port_runs_einat_then_qosify(dae: Online) -> None:
    assert hooks(dae.router, "pppoe-wan") == WAN
    assert _filters(dae.router) == ""


@spec(CAPABILITY, "Only dae on the LAN port", "Check the LAN port")
def test_lan_port_runs_only_dae(dae: Online) -> None:
    assert hooks(dae.router, "br-lan") == DAE


@spec(CAPABILITY, "Pass-through returns continue the chain", "ICMP reply on WAN ingress")
def test_icmp_reply_reaches_qosify_and_the_host(dae: Online) -> None:
    router = dae.router
    router.run("sysctl -qw kernel.bpf_stats_enabled=1")
    try:
        before = _qosify_runs(router, "ingress")
        time.sleep(PINGS * PING_INTERVAL)
        quiet = _qosify_runs(router, "ingress") - before
        assert quiet < PINGS // 4, f"{quiet} runs without pings: too busy a WAN to tell"
        before += quiet
        pinged = dae.client().run(
            *("ping", "-q", "-c", str(PINGS), "-i", str(PING_INTERVAL), "-W", "2"),
            DIRECT_TARGET[0],
        )
        received = re.search(r"(\d+) received", pinged)
        assert received is not None, pinged
        replies = int(received[1])
        assert replies > PINGS // 2, pinged
        # One run for each reply at least: the background alone makes far fewer.
        assert _qosify_runs(router, "ingress") - before >= replies
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


@spec(CAPABILITY, "Programs and order on the WAN port", "Kernel without tcx")
def test_qosify_falls_back_to_clsact(without_tcx: Online) -> None:
    router = without_tcx.router
    assert hooks(router, "pppoe-wan") == FALLBACK
    with qos.rules(router, f"dns:{qos.VOICE_NAMES}\tvoice"):
        before = qos.voice_packets(router)
        qos.send_by_name(without_tcx, 20)
        assert qos.voice_packets(router) >= before + 20
