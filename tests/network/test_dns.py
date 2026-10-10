"""network/dns: dnsmasq serves the LAN and asks dae first, the WAN's resolvers without it.

Names under any.example.net all resolve on the emulated internet, so every test
asks a name no cache has seen. The emulated internet lives in the documentation
ranges, which dnsmasq's rebind protection counts as private: the module lets
its zone through, as an operator does for a local domain.
"""

import re
import subprocess
import uuid
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.model.poll import until
from wrt_tests.sandbox.net import DIRECT_TARGET
from wrt_tests.services.datapath import DAE_CONFIG, dae_start

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.services.datapath import Online

CAPABILITY = "network/dns"
DAE_DNS_PORT = 5353
# dae names a query from its DNS listener in its log at trace level only, when it
# caches the answer ("Update DNS record cache").
DAE_TRACING = DAE_CONFIG.replace("log_level: debug", "log_level: trace")


def _fresh() -> str:
    return f"{uuid.uuid4().hex[:12]}.any.example.net"


def _dae_log(online: Online) -> str:
    return online.router.run("cat /var/log/dae/dae.log")


def _resolve(online: Online, name: str, **options: str) -> dict[str, object]:
    arguments = [f"--{key}={value}" for key, value in options.items()]
    return online.client().probe("resolve", name, "--server", online.router.address, *arguments)


pytestmark = pytest.mark.usefixtures("internet_zone")


@pytest.fixture(scope="module", autouse=True)
def dae_tracing(dae: Online) -> None:
    """Run dae logging at trace level for the module."""
    dae_start(dae.router, DAE_TRACING)


@pytest.fixture
def dae_restored(dae: Online) -> Iterator[Online]:
    """Start dae again after a test that stops it."""
    yield dae
    dae_start(dae.router, DAE_TRACING)


@spec(CAPABILITY, "dnsmasq remains the LAN DNS server", "Query a local hostname")
def test_local_names_stay_local(dae: Online) -> None:
    ipv4_b, _ = dae.addresses("client-b")
    assert _resolve(dae, "client-b.lan") == {"rcode": 0, "answers": [ipv4_b]}
    assert "client-b.lan" not in _dae_log(dae)


@spec(CAPABILITY, "External domains resolved by dae", "Query an external domain")
def test_external_names_go_through_dae(dae: Online) -> None:
    name = _fresh()
    assert _resolve(dae, name) == {"rcode": 0, "answers": [DIRECT_TARGET[0]]}
    assert re.search(rf"_qname={re.escape(name)}\.", _dae_log(dae))


@spec(CAPABILITY, "Fall back to upstream DNS without dae", "Resolve after dae stops")
def test_resolving_goes_on_without_dae(dae_restored: Online) -> None:
    router = dae_restored.router
    router.run("/etc/init.d/dae stop")
    until(lambda: router.returncode("pidof dae") != 0, timeout=60, what="dae gone")
    assert _resolve(dae_restored, _fresh()) == {"rcode": 0, "answers": [DIRECT_TARGET[0]]}


@spec(CAPABILITY, "dae DNS port not exposed", "Query dae's DNS port from LAN")
def test_dae_dns_port_is_closed_to_the_lan(dae: Online) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        _resolve(dae, _fresh(), port=str(DAE_DNS_PORT))
    assert "127.0.0.1:5353" in dae.router.run(f"ss -Hlun 'sport = :{DAE_DNS_PORT}'")
