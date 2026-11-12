"""network/dns: dnsmasq serves the LAN and asks honk first, the WAN's resolvers without it.

Names under any.example.net all resolve on the emulated internet, so every test
asks a name no cache has seen. The emulated internet lives in the documentation
ranges, which dnsmasq's rebind protection counts as private: the module lets
its zone through, as an operator does for a local domain.

honk names no query in its log; whether it resolved a name is what its DNS cache
holds, which the module reads through honk's native API.
"""

import json
import subprocess
import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import quote

import pytest

from wrt_tests import spec
from wrt_tests.model.poll import until
from wrt_tests.sandbox.net import DIRECT_TARGET
from wrt_tests.services import app
from wrt_tests.services.datapath import (
    NATIVE_API,
    PROXY_CONFIG,
    PROXY_HOOKS_L2,
    hooks,
    native_api,
    proxy_start,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.services.datapath import Online

CAPABILITY = "network/dns"
PROXY_DNS_PORT = 5353
DNS_CONFIG = PROXY_CONFIG + NATIVE_API


def _fresh() -> str:
    return f"{uuid.uuid4().hex[:12]}.any.example.net"


def _cached(online: Online, name: str) -> bool:
    """Return whether honk's DNS cache holds ``name``."""
    path = f"/api/v1/dns/cache?name={quote(name)}"
    status, body = native_api(online.client(), online.router.address, path)
    assert status == HTTPStatus.OK, (status, body)
    return int(json.loads(body)["total"]) > 0


def _resolve(online: Online, name: str, **options: str) -> dict[str, object]:
    arguments = [f"--{key}={value}" for key, value in options.items()]
    return online.client().probe("resolve", name, "--server", online.router.address, *arguments)


pytestmark = pytest.mark.usefixtures("internet_zone")


@pytest.fixture(scope="module", autouse=True)
def proxy_with_api(proxy: Online) -> None:
    """Run honk with its native API for the module, to read its DNS cache."""
    proxy_start(proxy.router, DNS_CONFIG)


@pytest.fixture
def proxy_restored(proxy: Online) -> Iterator[Online]:
    """Start honk again after a test that stops it."""
    yield proxy
    proxy_start(proxy.router, DNS_CONFIG)


@spec(CAPABILITY, "dnsmasq remains the LAN DNS server", "Query a local hostname")
def test_local_names_stay_local(proxy: Online) -> None:
    ipv4_b, _ = proxy.addresses("client-b")
    assert _resolve(proxy, "client-b.lan") == {"rcode": 0, "answers": [ipv4_b]}
    assert not _cached(proxy, "client-b.lan")


@spec(CAPABILITY, "External domains resolved by the proxy", "Query an external domain")
def test_external_names_go_through_honk(proxy: Online) -> None:
    name = _fresh()
    assert _resolve(proxy, name) == {"rcode": 0, "answers": [DIRECT_TARGET[0]]}
    assert _cached(proxy, name)


@spec(
    CAPABILITY,
    "DNS to private addresses reaches its server",
    "Query the router while the proxy runs",
)
def test_the_router_answers_its_own_names(proxy: Online) -> None:
    ipv4_b, _ = proxy.addresses("client-b")
    # A name dnsmasq answers itself: honk, which would intercept DNS to a
    # public resolver, leaves DNS to the router's address to dnsmasq.
    assert _resolve(proxy, "client-b.lan") == {"rcode": 0, "answers": [ipv4_b]}
    assert not _cached(proxy, "client-b.lan")


@spec(CAPABILITY, "Fall back to upstream DNS without the proxy", "Resolve after the proxy stops")
def test_resolving_goes_on_without_honk(proxy_restored: Online) -> None:
    router = proxy_restored.router
    router.run("/etc/init.d/honk stop")
    until(lambda: router.returncode("pidof honk-core") != 0, timeout=60, what="honk gone")
    assert _resolve(proxy_restored, _fresh()) == {"rcode": 0, "answers": [DIRECT_TARGET[0]]}


@spec(CAPABILITY, "Proxy DNS port not exposed", "Query the proxy's DNS port from LAN")
def test_honk_dns_port_is_closed_to_the_lan(proxy: Online) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        _resolve(proxy, _fresh(), port=str(PROXY_DNS_PORT))
    assert "127.0.0.1:5353" in proxy.router.run(f"ss -Hlun 'sport = :{PROXY_DNS_PORT}'")


# The last test: its Pod and data disk stay for the rest of the module.
@spec(CAPABILITY, "DNS to private addresses reaches its server", "Resolve a container's name")
def test_containers_resolve_through_their_network(app_pod: Online) -> None:
    router = app_pod.router
    # honk binds the container bridge, and passes its DNS to a private address.
    until(lambda: hooks(router, "podman0") == PROXY_HOOKS_L2, timeout=60, what="honk on podman0")
    answer = router.run(f"podman exec {app.CONTAINER} nslookup {app.POD} {app.GATEWAY}")
    assert app.ADDRESS in answer, answer
