"""The fixtures of the router online and what runs on it (module-boundaries D6).

A module dials in at the emulated ISP once; dae, the emulated internet's names
and CA, and the test app's Pod build on that session.
"""

from typing import TYPE_CHECKING

import pytest

from wrt_tests.device.trust import trust_ca
from wrt_tests.model.poll import until
from wrt_tests.services import app
from wrt_tests.services.datapath import Online, dae_start

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.device.router import Router
    from wrt_tests.device.storage import Disk
    from wrt_tests.sandbox.isp import Isp
    from wrt_tests.sandbox.net import Network


@pytest.fixture(scope="module")
def online(module_router: Router, isp: Isp, network: Network) -> Online:
    """Dial in at the ISP for the module."""
    return Online.dial(module_router, isp, network)


@pytest.fixture(scope="module")
def internet_zone(online: Online) -> Online:
    """Let the emulated internet's answers through dnsmasq's rebind protection.

    Its addresses are documentation ranges, which the protection counts as
    private; an operator lets a local domain through the same way. dnsmasq
    restarts to take it, and until it listens again, dae answers a LAN query to
    the router's port 53 itself (a query to a local socket is the one it leaves
    alone), so the fixture waits for dnsmasq.
    """
    router = online.router
    router.run(
        "uci add_list dhcp.@dnsmasq[0].rebind_domain=example.net && uci commit dhcp"
        " && /etc/init.d/dnsmasq reload"
    )
    until(
        lambda: f"{router.address}:53" in router.run("ss -Hlun 'sport = :53'"),
        timeout=60,
        what="dnsmasq listening again",
    )
    return online


@pytest.fixture(scope="module")
def dae(online: Online) -> Iterator[Online]:
    """Run dae with the test configuration for the module."""
    dae_start(online.router)
    yield online
    online.router.run("/etc/init.d/dae stop; uci set dae.config.enabled=0; uci commit dae")


@pytest.fixture(scope="module")
def trusted_ca(internet_zone: Online) -> Online:
    """Have the router resolve and trust the emulated internet's servers (test CA)."""
    trust_ca(internet_zone.router, internet_zone.network.workdir)
    return internet_zone


@pytest.fixture(scope="module")
def app_pod(trusted_ca: Online, data_disk: Disk, app_image: str) -> Online:
    """Declare the app Pod on the data disk and wait until wrt-containers has started it."""
    del data_disk  # requested for the Pod's place
    app.declare(trusted_ca.router, app_image)
    app.wait_running(trusted_ca.router)
    return trusted_ca
