"""Unit tests of wrt_tests.sandbox.net: the sandbox topology, built without the emulator.

The addresses and routes are those of r4s-ebpf-datapath design D11, written out
here rather than read back from ``TOPOLOGY``.
"""

from typing import TYPE_CHECKING

import pytest

from wrt_tests.sandbox.net import ip

if TYPE_CHECKING:
    from wrt_tests.sandbox.net import Network

# namespace -> (addresses on eth1 for isp / eth0 otherwise, default gateways)
INTERNET = {
    "isp": (
        ("203.0.113.1/24", "198.51.100.1/24", "2001:db8:ffff::1/64", "2001:db8:53::1/64"),
        (),
    ),
    "inet": (
        ("203.0.113.53/24", "203.0.113.10/24", "203.0.113.20/24", "2001:db8:ffff::53/64"),
        ("203.0.113.1", "2001:db8:ffff::1"),
    ),
    "proxy": (("198.51.100.53/24", "2001:db8:53::53/64"), ("198.51.100.1", "2001:db8:53::1")),
    "wg-peer": (("203.0.113.60/24", "2001:db8:ffff::60/64"), ("203.0.113.1", "2001:db8:ffff::1")),
    "ts-peer": (("203.0.113.70/24", "2001:db8:ffff::70/64"), ("203.0.113.1", "2001:db8:ffff::1")),
}


@pytest.mark.parametrize("name", INTERNET)
def test_internet_hosts_have_their_addresses_and_routes(network: Network, name: str) -> None:
    addresses, gateways = INTERNET[name]
    device = "eth1" if name == "isp" else "eth0"
    shown = network[name].run("ip", "-o", "addr", "show", "dev", device).split()
    assert set(addresses) <= set(shown)
    for gateway, family in zip(gateways, ("-4", "-6"), strict=False):
        route = network[name].run("ip", family, "route", "show", "default").split()
        assert route[:3] == ["default", "via", gateway]


def test_isp_forwards_between_internet_hosts(network: Network) -> None:
    for target in ("203.0.113.10", "2001:db8:ffff::10"):
        network["proxy"].run("ping", "-c", "1", "-W", "2", target)


def test_internet_resolver_serves_example_test(network: Network) -> None:
    for kind, answer in (("A", "203.0.113.20"), ("AAAA", "2001:db8:ffff::20")):
        seen = network["proxy"].probe(
            "resolve", "proxied.example.net", "--server", "203.0.113.53", "--type", kind
        )
        assert seen == {"rcode": 0, "answers": [answer]}


@pytest.mark.parametrize(
    ("bridge", "ports"),
    [
        ("br-lan", {"emu-lan", "v0-client-a", "v0-client-b"}),
        ("br-wan", {"emu-wan", "v0-isp"}),
        ("br-inet", {"v1-isp", "v0-inet", "v0-proxy"}),
    ],
)
def test_bridges_join_their_ports(network: Network, bridge: str, ports: set[str]) -> None:
    del network  # requested for the bridges
    shown = ip("-o", "link", "show", "master", bridge)
    assert {line.split(": ")[1].split("@")[0] for line in shown.splitlines()} >= ports


@pytest.mark.parametrize(
    ("server", "path"),
    [("registry.example.net", "/v2/"), ("headscale.example.net", "/health")],
)
def test_servers_answer_over_tls_of_the_test_ca(network: Network, server: str, path: str) -> None:
    # r4s-services D10: the registry and headscale on inet, named by the
    # sandbox's hosts file and by the internet's resolver.
    ca = network.workdir / "pki" / "ca.crt"
    network["proxy"].run(
        "curl", "-sfo", "/dev/null", "--cacert", str(ca), f"https://{server}{path}"
    )
    answer = network["proxy"].probe("resolve", server, "--server", "203.0.113.53")
    assert answer["answers"]
