"""services/vpn: WireGuard and Tailscale into the LAN, and how each passes dae.

wg-peer connects over WireGuard and routes the LAN and the proxied target
through its tunnel; ts-peer is a tailnet node that takes the LAN through the
router's subnet route and, when asked, the router as its exit node. dae is on:
tailnet traffic is split by its rules, WireGuard traffic goes direct.
"""

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.datapath import hooks
from wrt_tests.net import PROXIED_TARGET, PROXY
from wrt_tests.poll import until

if TYPE_CHECKING:
    from wrt_tests.datapath import Online
    from wrt_tests.net import Netns
    from wrt_tests.vpn import Tailnet, WireGuard

CAPABILITY = "services/vpn"
REPO = Path(__file__).resolve().parents[2]
MARKS_CHECK = REPO / "scripts" / "marks-check.sh"
MARKS = REPO / "config" / "marks.tsv"
LAN_ADDRESS = "10.0.0.1"
# The router's services for the LAN alone: SSH and LuCI.
LAN_ONLY_PORTS = (22, 80)
BIND_TIMEOUT = 60
# dae's programs for an interface without Ethernet headers, on both directions.
TUN_HOOKS = ("tcx/ingress", "tcx/egress")


@pytest.fixture(scope="module")
def remote(dae: Online, lan_host: Netns) -> Online:
    """Run dae, and a server on a LAN host for the peers to reach."""
    del lan_host  # serving for the module
    return dae


@spec(CAPABILITY, "WireGuard remote access", "Remote device connects")
def test_wireguard_reaches_the_lan(remote: Online, wireguard: WireGuard) -> None:
    host = remote.addresses("client-a")[0]
    assert wireguard.peer.probe("tcp", host)["address"]
    for port in LAN_ONLY_PORTS:
        assert remote.client().probe("connect", LAN_ADDRESS, "--port", str(port)) == {
            "connection": "accepted"
        }
        assert wireguard.peer.probe("connect", LAN_ADDRESS, "--port", str(port)) == {
            "connection": "refused"
        }
    # The image (/rom) holds no key: the test wrote the one wg0 has.
    assert remote.router.returncode("grep -rqs private_key /rom/etc") != 0


@spec(CAPABILITY, "Relation to the transparent proxy", "WireGuard device reaches the internet")
def test_wireguard_goes_direct(remote: Online, wireguard: WireGuard) -> None:
    # The proxied target is one dae would proxy for the LAN.
    assert wireguard.peer.probe("tcp", PROXIED_TARGET[0])["address"] == remote.wan_address


@spec(CAPABILITY, "Tailscale networking", "Reach the LAN via subnet route")
def test_tailnet_reaches_the_lan(remote: Online, tailnet: Tailnet) -> None:
    host = remote.addresses("client-a")[0]
    assert tailnet.peer.probe("tcp", host)["address"]
    assert "10.0.0.0/24 dev tailscale0" in tailnet.peer.run("ip", "route", "show", "table", "52")
    # The image (/rom) holds no tailnet state: the test logged the router in.
    assert remote.router.returncode("test -e /rom/etc/tailscale/tailscaled.state") != 0


@spec(CAPABILITY, "Relation to the transparent proxy", "Tailnet device reaches a proxied target")
def test_tailnet_is_split_by_dae(remote: Online, tailnet: Tailnet) -> None:
    until(
        lambda: _dae_bound(remote, "tailscale0"),
        timeout=BIND_TIMEOUT,
        what="dae on tailscale0",
    )
    tailnet.use_exit_node(on=True)
    try:
        seen = until(
            lambda: _probe_or_none(tailnet.peer, PROXIED_TARGET[0]),
            timeout=BIND_TIMEOUT,
            what="the proxied target through the exit node",
        )
        assert seen["address"] == PROXY[0]
    finally:
        tailnet.use_exit_node(on=False)


def _dae_bound(remote: Online, device: str) -> bool:
    """Return whether dae's LAN programs sit on both directions of ``device``."""
    found = hooks(remote.router, device)
    return set(found) == set(TUN_HOOKS) and all(
        any(name.startswith("tproxy_lan_") for name in found[hook]) for hook in TUN_HOOKS
    )


def _probe_or_none(peer: Netns, host: str) -> dict[str, object] | None:
    try:
        return dict(peer.probe("tcp", host))
    except subprocess.CalledProcessError:
        return None


@spec(CAPABILITY, "Mark bit registration", "Check the allocation table")
def test_tailscale_marks_are_registered(remote: Online, tailnet: Tailnet) -> None:
    del tailnet  # logged in: its firewall rules are in place
    rows = [line.split("\t") for line in MARKS.read_text().splitlines()[1:]]
    (mask,) = (int(row[0], 16) for row in rows if row[1] == "tailscale")
    subprocess.run([MARKS_CHECK], check=True, capture_output=True)
    # The marks tailscaled's own nftables rules set and match lie within its mask.
    ruleset = remote.router.run("nft list ruleset")
    tables = re.split(r"^table ", ruleset, flags=re.MULTILINE)
    theirs = [table for table in tables if table and not table.startswith("inet fw4")]
    marks = {
        int(value, 16)
        for table in theirs
        for line in table.splitlines()
        if "mark" in line
        for value in re.findall(r"(?:==|\|) (0x[0-9a-f]+)", line)
    }
    assert marks
    assert all(mark & ~mask == 0 for mark in marks), [hex(mark) for mark in marks]
