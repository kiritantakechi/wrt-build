"""network/nat: einat's full-cone NAT44 and what falls back to masquerade.

dae stays off in this module: every flow goes direct, so what the internet sees
is einat's work (or masquerade's) alone.
"""

import json
import re
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.datapath import EINAT, hooks
from wrt_tests.net import DIRECT_TARGET, PROXIED_TARGET
from wrt_tests.netprobe import HTTP_PORT
from wrt_tests.poll import until

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.datapath import Online
    from wrt_tests.net import Netns

CAPABILITY = "network/nat"
# einat's public ports (its UCI default) and the kernel's local ephemeral ports.
EINAT_PORTS = range(20000, 30000)
LOCAL_PORTS = range(32768, 61000)
INBOUND_MARK = "0x20000000"
NEVER_CONTACTED = "203.0.113.53"  # an address of the internet host no test sends to first
RECOVERY = 60
HEALTHCHECK = "/etc/healthcheck.d/50-einat"


class Listener:
    """A UDP listener on a LAN client, waiting for one datagram."""

    def __init__(self, client: Netns, port: int, timeout: float = 10) -> None:
        """Start listening and wait until the socket is bound."""
        command = ("listen", "--port", str(port), "--timeout", str(timeout))
        self.process = subprocess.Popen(
            client.argv(sys.executable, "-m", "wrt_tests.netprobe", *command),
            stdout=subprocess.PIPE,
        )
        until(lambda: client.run("ss", "-Hlun", f"sport = :{port}"), timeout=10, what="listener")

    def received(self) -> bool:
        """Return whether the datagram arrived before the listener gave up."""
        self.process.communicate(timeout=60)
        return self.process.wait() == 0


def _map(online: Online, port: int, target: str = DIRECT_TARGET[0]) -> int:
    """Send from a LAN socket on ``port`` to ``target``; return the public port it got."""
    seen = online.client().probe("udp", target, "--source-port", str(port))
    assert seen["address"] == online.wan_address
    assert isinstance(seen["port"], int)
    return seen["port"]


def _inbound_accepted(online: Online) -> int:
    """Return the packets fw4's accept-by-mark rules have counted, or -1 without them."""
    ruleset = online.router.run("nft list chain inet fw4 forward_wan")
    rule = rf"meta mark & {INBOUND_MARK} == {INBOUND_MARK} counter packets (\d+)"
    counts = [int(count) for count in re.findall(rule, ruleset)]
    return sum(counts) if counts else -1


def _einat_rules(online: Online) -> bool:
    """Return whether fw4 has einat's rules (procd hands them over with einat)."""
    return "ubus:einat" in online.router.run("nft list ruleset")


def _einat_attached(online: Online) -> None:
    until(
        lambda: hooks(online.router, "pppoe-wan").get("tcx/ingress") == EINAT["tcx/ingress"],
        timeout=RECOVERY,
        what="einat on pppoe-wan",
    )


@pytest.fixture
def einat_restored(online: Online) -> Iterator[Online]:
    """Put einat back as it was after a test that stops, detaches or reconfigures it."""
    yield online
    online.router.run("/etc/init.d/einat restart")
    _einat_attached(online)


@spec(CAPABILITY, "Full-cone NAT44", "Endpoint-independent mapping")
def test_mapping_is_endpoint_independent(online: Online) -> None:
    first, second = _map(online, 41000), _map(online, 41000, PROXIED_TARGET[0])
    assert first == second
    assert first in EINAT_PORTS


@spec(CAPABILITY, "Full-cone NAT44", "Endpoint-independent filtering")
def test_filtering_is_endpoint_independent(online: Online) -> None:
    public = _map(online, 41001)
    listener = Listener(online.client(), 41001)
    online.network["inet"].probe(
        "send", online.wan_address, "--port", str(public), "--bind", NEVER_CONTACTED
    )
    assert listener.received()


@spec(
    CAPABILITY,
    "Accept only einat-translated inbound connections",
    "Inbound packet with spoofed destination",
)
def test_spoofed_inbound_is_dropped(online: Online) -> None:
    # Structurally: einat's mark is the only way from wan into lan for a new flow
    # (OpenWrt's default accepts of ESP and ISAKMP are gone).
    accepts = [
        line
        for line in online.router.run("nft list chain inet fw4 forward_wan").splitlines()
        if "accept" in line and "icmpv6" not in line
    ]
    assert accepts, "no accept rule at all"
    assert all(f"meta mark & {INBOUND_MARK} == {INBOUND_MARK}" in line for line in accepts), accepts
    ipv4, _ = online.addresses()
    isp = online.network["isp"]
    mac = online.router.run("cat /sys/class/net/eth0/address")
    # Through the PPP session, routed by the ISP to an internal address...
    isp.run("ip", "route", "replace", "10.0.0.0/24", "dev", online.session.interface)
    try:
        listener = Listener(online.client(), 41002)
        isp.probe("send", ipv4, "--port", "41002")
        assert not listener.received()
    finally:
        isp.run("ip", "route", "del", "10.0.0.0/24")
    # ...and as a bare frame on the Ethernet segment under PPPoE.
    listener = Listener(online.client(), 41003)
    isp.probe(
        "inject",
        "eth0",
        "--mac",
        mac,
        "--source",
        NEVER_CONTACTED,
        "--destination",
        ipv4,
        "--port",
        "41003",
    )
    assert not listener.received()


@spec(
    CAPABILITY,
    "Accept only einat-translated inbound connections",
    "Inbound packet to a mapped port",
)
def test_inbound_to_a_mapped_port_is_accepted(online: Online, einat_restored: Online) -> None:
    del einat_restored
    # The einat our mark patch applies to.
    # einat prints its version first: "version: 0.1.11 features: ..."
    assert online.router.run("einat --version").split()[:2] == ["version:", "0.1.11"]
    before = _inbound_accepted(online)
    public = _map(online, 41004)
    listener = Listener(online.client(), 41004)
    online.network["inet"].probe(
        "send", online.wan_address, "--port", str(public), "--bind", NEVER_CONTACTED
    )
    assert listener.received()
    # The patch's mark is what let it in (design D2, D3): without --inbound-mark
    # einat marks nothing, and the same packet stays out (task 1.5).
    assert _inbound_accepted(online) > before >= 0
    online.router.run("uci set einat.config.inbound_mark=0 && /etc/init.d/einat restart")
    try:
        _einat_attached(online)
        until(lambda: _inbound_accepted(online) == -1, timeout=RECOVERY, what="no mark rule")
        public = _map(online, 41005)
        listener = Listener(online.client(), 41005, timeout=5)
        online.network["inet"].probe(
            "send", online.wan_address, "--port", str(public), "--bind", NEVER_CONTACTED
        )
        assert not listener.received()
    finally:
        online.router.run("uci revert einat")


@spec(CAPABILITY, "Other protocols still use masquerade", "IPsec ESP traffic")
def test_esp_is_masqueraded(online: Online) -> None:
    assert online.client().probe("esp", DIRECT_TARGET[0]) == {"address": online.wan_address}


@spec(CAPABILITY, "Fall back to masquerade when einat stops", "Stop einat")
def test_stopping_einat_falls_back_to_masquerade(online: Online, einat_restored: Online) -> None:
    del einat_restored
    online.router.run("/etc/init.d/einat stop")
    assert "tcx/ingress" not in hooks(online.router, "pppoe-wan")
    # fw4 reloads without einat's rules a moment later; masquerade then applies.
    until(lambda: not _einat_rules(online), timeout=RECOVERY, what="einat's rules withdrawn")
    seen = online.client().probe("udp", DIRECT_TARGET[0], "--source-port", "41006")
    # Masquerade keeps a free source port; einat would have picked one of its own.
    assert (seen["address"], seen["port"]) == (online.wan_address, 41006)
    assert online.client().probe("tcp", DIRECT_TARGET[0])["address"] == online.wan_address
    # The accept-by-mark rule went with einat: nothing unasked comes in.
    assert _inbound_accepted(online) == -1
    listener = Listener(online.client(), 41006, timeout=5)
    online.network["inet"].probe(
        "send", online.wan_address, "--port", str(seen["port"]), "--bind", NEVER_CONTACTED
    )
    assert not listener.received()


@spec(CAPABILITY, "Port range isolated from local ports", "Local connections not rewritten")
def test_local_connections_keep_their_port(online: Online) -> None:
    body = online.router.run(f"uclient-fetch -qO- http://{DIRECT_TARGET[0]}:{HTTP_PORT}/")
    seen = json.loads(body)
    assert seen["address"] == online.wan_address
    assert seen["port"] in LOCAL_PORTS
    # The router's own conntrack entry has the same port: nothing rewrote it.
    conntrack = online.router.run("cat /proc/net/nf_conntrack")
    assert f"dst={DIRECT_TARGET[0]} sport={seen['port']} dport={HTTP_PORT}" in conntrack
    # The ranges cannot meet (design D6): einat's ports lie below the kernel's.
    assert online.router.run("uci get einat.config.ports") == "20000-29999"
    assert (
        int(online.router.run("cut -f1 /proc/sys/net/ipv4/ip_local_port_range")) > EINAT_PORTS.stop
    )


@spec(CAPABILITY, "No IPv6 translation", "LAN reaches external hosts over IPv6")
def test_ipv6_is_not_translated(online: Online) -> None:
    _, ipv6 = online.addresses()
    assert online.client().probe("tcp", DIRECT_TARGET[1])["address"] == ipv6


@spec(CAPABILITY, "Automatic recovery after redial", "Redial after PPPoE disconnect")
def test_full_cone_after_redial(online: Online) -> None:
    previous = online.redial()
    assert online.wan_address != previous.peer
    assert online.recovery <= RECOVERY
    first, second = _map(online, 41007), _map(online, 41007, PROXIED_TARGET[0])
    assert first == second
    listener = Listener(online.client(), 41007)
    online.network["inet"].probe(
        "send", online.wan_address, "--port", str(first), "--bind", NEVER_CONTACTED
    )
    assert listener.received()


@spec(CAPABILITY, "Register a health check", "PPPoE not yet connected")
def test_health_check(online: Online, einat_restored: Online) -> None:
    del einat_restored
    router = online.router
    assert router.returncode(HEALTHCHECK) == 0
    # No pppoe-wan yet: einat waits for it, and the check passes.
    router.run("ifdown wan")
    try:
        until(
            lambda: router.returncode("[ -e /sys/class/net/pppoe-wan ]") != 0,
            timeout=30,
            what="pppoe-wan gone",
        )
        assert router.returncode("pidof einat >/dev/null") == 0
        assert router.returncode(HEALTHCHECK) == 0
    finally:
        router.run("ifup wan")
        online.reconnected()
    # Task 4.3: einat not running fails, and so does einat not attached to pppoe-wan.
    router.run("/etc/init.d/einat stop")
    assert router.returncode(HEALTHCHECK) != 0
    router.run("/etc/init.d/einat start")
    until(lambda: router.returncode(HEALTHCHECK) == 0, timeout=RECOVERY, what="einat attached")
    for link in re.findall(r"link_id (\d+)", router.run("bpftool net show dev pppoe-wan")):
        router.run(f"bpftool link detach id {link}")
    assert router.returncode(HEALTHCHECK) != 0
