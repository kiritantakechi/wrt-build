"""network/wan: PPPoE without built-in credentials, MSS clamping, prefix delegation, the flowtable.

The first two tests look at the router as it boots (its snapshot); the rest share
one router online behind the emulated ISP.
"""

import ipaddress
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.model.poll import until
from wrt_tests.sandbox.isp import DELEGATED_PREFIX, POOL_SIZE, POOL_START
from wrt_tests.sandbox.net import DIRECT_TARGET, IPERF_PORTS

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from wrt_tests.device.router import Router
    from wrt_tests.model.boards import Board
    from wrt_tests.services.datapath import Online

CAPABILITY = "network/wan"
UPGRADE_IMAGE = "/tmp/sysupgrade.tar.gz"  # noqa: S108 (a path on the router)
# PPPoE takes 8 of Ethernet's 1500 bytes; a TCP segment's headers take 40 more.
PATH_MTU = 1492
MSS_MAX = PATH_MTU - 40
DOWNLOAD_SECONDS = 20


@spec(CAPABILITY, "PPPoE dial-up", "Image contains no credentials")
def test_image_has_no_credentials(router: Router, board: Board) -> None:
    assert router.run("uci get network.wan.proto") == "pppoe"
    assert router.run("uci get network.wan.device") == board.wan.device
    for option in ("username", "password"):
        assert router.returncode(f"uci -q get network.wan.{option}") != 0, option
    # The rest of the datapath's defaults (uci-defaults 91-wrt-datapath).
    assert router.run("uci get network.wan6.device") == "@wan"
    assert router.run("uci get network.lan.ip6assign") == "64"
    assert router.run("uci get firewall.@defaults[0].flow_offloading") == "1"


@spec(CAPABILITY, "PPPoE dial-up", "Upgrade keeps the pushed configuration")
def test_upgrade_keeps_the_pushed_configuration(router: Router, upgrade_image: Path) -> None:
    # The defaults apply to a fresh configuration only; one that an upgrade
    # carries over keeps its values, however they differ (uci-defaults, keep.d).
    changes = {
        "network.wan.username": "someone",
        "network.wan.password": "secret",
        "network.lan.ip6assign": "60",
        "firewall.@defaults[0].flow_offloading": "0",
        "dhcp.@dnsmasq[0].strictorder": "0",
        "qosify.wan.bandwidth_up": "30mbit",
    }
    router.run(" && ".join(f"uci set {key}={value}" for key, value in changes.items()))
    router.run("uci commit")
    router.put(upgrade_image, UPGRADE_IMAGE)
    previous_boot = router.boot_id()
    router.detach(f"sleep 1; sysupgrade {UPGRADE_IMAGE}")
    router.wait_rebooted(previous_boot)
    assert {key: router.run(f"uci get {key}") for key in changes} == changes


@spec(CAPABILITY, "PPPoE dial-up", "Dial after pushing credentials")
def test_dial_after_pushing_credentials(online: Online) -> None:
    shown = online.router.run("ip -4 -o addr show dev pppoe-wan").split()
    address = shown[shown.index("inet") + 1].split("/")[0]
    offset = int(ipaddress.IPv4Address(address)) - int(ipaddress.IPv4Address(POOL_START))
    assert 0 <= offset < POOL_SIZE
    assert address == online.wan_address


@spec(CAPABILITY, "MSS clamping", "LAN host opens a TCP connection")
def test_mss_fits_the_path(online: Online) -> None:
    client = online.client()
    seen = client.probe("tcp", DIRECT_TARGET[0])
    assert isinstance(seen["mss"], int)
    assert seen["mss"] <= MSS_MAX
    # The path MTU itself: the largest unfragmented ping fits, one byte more does not.
    payload = PATH_MTU - 28
    client.run("ping", "-c", "1", "-W", "2", "-M", "do", "-s", str(payload), DIRECT_TARGET[0])
    with pytest.raises(subprocess.CalledProcessError):
        client.run(
            "ping", "-c", "1", "-W", "2", "-M", "do", "-s", str(payload + 1), DIRECT_TARGET[0]
        )


@spec(CAPABILITY, "IPv6 prefix delegation", "LAN host gets IPv6")
def test_lan_host_gets_ipv6(online: Online) -> None:
    _, ipv6 = online.addresses()
    assert ipaddress.IPv6Address(ipv6) in DELEGATED_PREFIX
    # Reaches the IPv6 internet as itself: no NAT66.
    assert online.client().probe("tcp", DIRECT_TARGET[1])["address"] == ipv6


@spec(CAPABILITY, "IPv6 inbound firewall", "External host connects to an internal IPv6 address")
def test_inbound_ipv6_is_rejected(online: Online) -> None:
    _, ipv6 = online.addresses()
    client = online.client()
    server = client.spawn(sys.executable, "-m", "wrt_tests.sandbox.netprobe", "serve")
    try:
        until(lambda: client.run("ss", "-Hltn", "sport = :8007"), timeout=10, what="netprobe")
        # The LAN reaches the server; the internet does not.
        assert online.client("client-b").probe("tcp", ipv6)["address"]
        with pytest.raises(subprocess.CalledProcessError):
            online.network["inet"].probe("tcp", ipv6)
    finally:
        server.terminate()
        server.wait()


@spec(
    CAPABILITY,
    "Software acceleration does not bypass NAT",
    "Check acceleration and source address while downloading",
)
def test_offloaded_flows_keep_the_wan_address(
    online: Online, record_testsuite_property: Callable[[str, object], None]
) -> None:
    client = online.client()
    download = client.spawn(
        "iperf3",
        "--client",
        DIRECT_TARGET[0],
        "--port",
        str(IPERF_PORTS[0]),
        "--reverse",
        "--time",
        str(DOWNLOAD_SECONDS),
    )
    try:
        flow = until(
            lambda: [
                line
                for line in online.router.run("cat /proc/net/nf_conntrack").splitlines()
                if f"dport={IPERF_PORTS[0]}" in line and "[OFFLOAD]" in line
            ],
            timeout=DOWNLOAD_SECONDS,
            what="offloaded iperf3 flow",
        )
        record_testsuite_property("offloaded flow", flow[0])
        for _ in range(3):
            assert client.probe("tcp", DIRECT_TARGET[0])["address"] == online.wan_address
    finally:
        download.terminate()
        download.wait()
