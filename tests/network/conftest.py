"""Fixtures of the network tests: the router online behind the emulated ISP (r4s-ebpf-datapath D11).

A PPP session does not survive a jump back to a snapshot (the ISP would still
hold the old one), so each module takes the router from its post-boot snapshot
once, dials, and keeps it online for all of its tests; a test puts back what it
changed. At the end of the module the router returns to its snapshot.
"""

from typing import TYPE_CHECKING

import pytest

from wrt_tests.datapath import Online, dae_start

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.isp import Isp
    from wrt_tests.net import Network
    from wrt_tests.router import Router


@pytest.fixture(scope="module")
def online(booted_router: Router, isp: Isp, network: Network) -> Iterator[Online]:
    """Dial from the post-boot state; return to it after the module."""
    booted_router.reset()
    yield Online.dial(booted_router, isp, network)
    booted_router.reset()


@pytest.fixture(scope="module")
def dae(online: Online) -> Iterator[Online]:
    """Run dae with the test configuration for the module."""
    dae_start(online.router)
    yield online
    online.router.run("/etc/init.d/dae stop; uci set dae.config.enabled=0; uci commit dae")
