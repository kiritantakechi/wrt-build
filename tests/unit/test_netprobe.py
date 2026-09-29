"""Unit tests of wrt_tests.netprobe: every mode between two plain network namespaces.

``solicit-prefix`` needs a DHCPv6 server on a PPP link, and ``solicit-router`` a
router; test_isp and the network tests cover them.
"""

import json
import subprocess
import sys
import time
from typing import TYPE_CHECKING, NamedTuple

import pytest

from wrt_tests.net import Netns, ip
from wrt_tests.netprobe import BIG, PORT

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

SERVER = ("192.0.2.200", "2001:db8:1::200")
CLIENT = ("192.0.2.100", "2001:db8:1::100")
# A second address of the server: answers must come from the address asked.
SECOND = ("192.0.2.201", "2001:db8:1::201")


class Pair(NamedTuple):
    """Two namespaces joined by a veth; the server runs netprobe and dnsmasq."""

    client: Netns
    server: Netns


@pytest.fixture(scope="module")
def pair(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Pair]:
    """Build the pair and start the server's daemons."""
    workdir: Path = tmp_path_factory.mktemp("netprobe")
    with Netns("probe-server") as server, Netns("probe-client") as client:
        ip(
            *("link", "add", "eth0", "netns", str(server.pid), "type", "veth"),
            *("peer", "name", "eth0", "netns", str(client.pid)),
        )
        for netns, addresses in ((server, SERVER), (client, CLIENT)):
            netns.run("ip", "link", "set", "lo", "up")
            netns.run("ip", "link", "set", "eth0", "up")
            netns.run("ip", "addr", "add", f"{addresses[0]}/24", "dev", "eth0")
            netns.run("ip", "addr", "add", f"{addresses[1]}/64", "dev", "eth0", "nodad")
        for address, length in zip(SECOND, (24, 64), strict=True):
            server.run("ip", "addr", "add", f"{address}/{length}", "dev", "eth0", "nodad")
        daemons = [
            server.spawn(sys.executable, "-m", "wrt_tests.netprobe", "serve"),
            server.spawn(
                "dnsmasq",
                "--keep-in-foreground",
                "--conf-file=/dev/null",
                "--user=",
                "--group=",
                "--pid-file=",
                f"--log-facility={workdir / 'dnsmasq.log'}",
                "--no-resolv",
                "--no-hosts",
                "--bind-interfaces",
                f"--listen-address={SERVER[0]}",
                "--host-record=probe.example.net,{},{}".format(*SERVER),
            ),
        ]
        while not server.run("ss", "-Hln", f"sport = :{PORT}"):
            time.sleep(0.1)
        try:
            yield Pair(client, server)
        finally:
            for daemon in daemons:
                daemon.terminate()
                daemon.wait()


@pytest.fixture
def client(pair: Pair) -> Netns:
    return pair.client


@pytest.mark.parametrize("family", [0, 1], ids=["ipv4", "ipv6"])
def test_tcp_reports_the_peer_and_mss(client: Netns, family: int) -> None:
    seen = client.probe("tcp", SERVER[family])
    assert seen["address"] == CLIENT[family]
    assert isinstance(seen["mss"], int)
    assert 1200 < seen["mss"] <= 1460  # noqa: PLR2004


@pytest.mark.parametrize("family", [0, 1], ids=["ipv4", "ipv6"])
def test_connect_tells_accepted_from_refused(client: Netns, family: int) -> None:
    assert client.probe("connect", SERVER[family], "--port", str(PORT)) == {
        "connection": "accepted"
    }
    assert client.probe("connect", SERVER[family], "--port", "9") == {"connection": "refused"}


@pytest.mark.parametrize("family", [0, 1], ids=["ipv4", "ipv6"])
def test_udp_reports_the_peer(client: Netns, family: int) -> None:
    seen = client.probe("udp", SERVER[family], "--source-port", "40000")
    assert (seen["address"], seen["port"]) == (CLIENT[family], 40000)


@pytest.mark.parametrize("family", [0, 1], ids=["ipv4", "ipv6"])
def test_answers_come_from_the_address_asked(client: Netns, family: int) -> None:
    assert client.probe("udp", SECOND[family])["from"] == SECOND[family]
    assert client.probe("esp", SECOND[family]) == {"address": CLIENT[family]}


@pytest.mark.parametrize("family", [0, 1], ids=["ipv4", "ipv6"])
def test_http_reports_the_peer(client: Netns, family: int) -> None:
    host = f"[{SERVER[1]}]" if family else SERVER[0]
    fetch = f"import urllib.request as u; print(u.urlopen('http://{host}/').read().decode())"
    seen = json.loads(client.run(sys.executable, "-c", fetch))
    assert seen["address"] == CLIENT[family]


def test_big_reply_arrives_whole(client: Netns) -> None:
    assert client.probe("udp", SERVER[0], "--big")["size"] == BIG


@pytest.mark.parametrize("family", [0, 1], ids=["ipv4", "ipv6"])
def test_esp_is_answered_with_the_source(client: Netns, family: int) -> None:
    assert client.probe("esp", SERVER[family], "--spi", "0x1234") == {"address": CLIENT[family]}


def test_listen_receives_what_send_sends(pair: Pair) -> None:
    command = (sys.executable, "-m", "wrt_tests.netprobe", "listen", "--port", "40001")
    with subprocess.Popen(pair.client.argv(*command), stdout=subprocess.PIPE) as listener:
        while not pair.client.run("ss", "-Hlun", "sport = :40001"):
            time.sleep(0.1)
        sent = pair.server.probe("send", CLIENT[0], "--port", "40001", "--payload", "ping")
        seen = json.loads(listener.communicate(timeout=10)[0])
    assert seen == {"address": SERVER[0], "port": sent["port"], "payload": "ping"}


@pytest.mark.parametrize(("kind", "family"), [("A", 0), ("AAAA", 1)])
def test_resolve_returns_the_records(client: Netns, kind: str, family: int) -> None:
    seen = client.probe("resolve", "probe.example.net", "--server", SERVER[0], "--type", kind)
    assert seen == {"rcode": 0, "answers": [SERVER[family]]}


def test_resolve_reports_an_unknown_name(client: Netns) -> None:
    seen = client.probe("resolve", "missing.example.net", "--server", SERVER[0])
    assert seen["answers"] == []
