"""Unit tests of wrt_tests.sandbox.isp: a pppd in the sandbox dials the emulated ISP.

The dialer uses PPPoE in user mode as the ISP does (the host has no pppoe.ko);
the router dials the same ISP with the kernel's PPPoE.
"""

import ipaddress
import subprocess
from typing import TYPE_CHECKING

import pytest

from wrt_tests.model.poll import until
from wrt_tests.sandbox.isp import DELEGATED_PREFIX, DNS, LOGIN, POOL_SIZE, POOL_START
from wrt_tests.sandbox.net import Namespace, Port

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from wrt_tests.sandbox.isp import Isp
    from wrt_tests.sandbox.net import Netns, Network

UP_TIMEOUT = 30


def _in_pool(address: str) -> bool:
    offset = int(ipaddress.IPv4Address(address)) - int(ipaddress.IPv4Address(POOL_START))
    return 0 <= offset < POOL_SIZE


@pytest.fixture(scope="module")
def dialer(network: Network) -> Netns:
    return network.add(Namespace("dialer", ports=(Port("br-wan"),)))


class Dial:
    """One pppd session of the dialer; ``address`` is what the ISP gave it."""

    def __init__(self, dialer: Netns) -> None:
        """Dial and wait for IPCP."""
        self.dialer = dialer
        self.pppd = dialer.spawn(
            *("pppd", "pty", "pppoe -I eth0", "user", LOGIN[0], "password", LOGIN[1]),
            *("nodetach", "noauth", "noipdefault", "+ipv6", "noccp", "novj"),
        )
        self.address = until(self._address, timeout=UP_TIMEOUT, what="IPCP")

    def _address(self) -> str | None:
        try:
            shown = self.dialer.run("ip", "-4", "-o", "addr", "show", "dev", "ppp0").split()
        except subprocess.CalledProcessError:  # no ppp0 yet
            return None
        return shown[3].split("/")[0] if "inet" in shown else None

    def offer(self) -> dict[str, object]:
        """Solicit a prefix once kea runs for the session (IPv6CP comes up on its own)."""

        def attempt() -> dict[str, object] | None:
            try:
                return self.dialer.probe("solicit-prefix", "ppp0")
            except subprocess.CalledProcessError:
                return None

        return until(attempt, timeout=UP_TIMEOUT, what="DHCPv6 advertise")

    def ended(self) -> None:
        """Wait for pppd to exit after the ISP hung up."""
        self.pppd.wait(timeout=UP_TIMEOUT)


@pytest.fixture
def dial(dialer: Netns) -> Iterator[Callable[[], Dial]]:
    dials: list[Dial] = []

    def start() -> Dial:
        dials.append(Dial(dialer))
        return dials[-1]

    yield start
    for session in dials:
        session.pppd.terminate()
        session.pppd.wait()


def test_dial_gets_a_pool_address_and_a_prefix(dial: Callable[[], Dial], isp: Isp) -> None:
    session = dial()
    assert _in_pool(session.address)
    assert isp.session(session.address).interface.startswith("ppp")
    assert session.offer() == {"prefix": str(DELEGATED_PREFIX), "dns": [DNS[1]]}


def test_redial_gets_a_different_address(dial: Callable[[], Dial], isp: Isp) -> None:
    first = dial()
    isp.hang_up(isp.session(first.address))
    first.ended()
    second = dial()
    assert second.address != first.address
    assert _in_pool(second.address)


def test_wrong_password_is_refused(dialer: Netns) -> None:
    pppd = dialer.spawn(
        *("pppd", "pty", "pppoe -I eth0", "user", LOGIN[0], "password", "wrong"),
        *("nodetach", "noauth", "noipdefault", "maxfail", "1"),
    )
    assert pppd.wait(timeout=UP_TIMEOUT) != 0
