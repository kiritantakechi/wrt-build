"""Fixtures of every system test: the sandbox network, the emulator and the router.

The session boots the shipped image once and snapshots it; every test that uses
``router`` starts from that snapshot.

A PPP session does not survive a jump back to the snapshot (the ISP would still
hold the old one), and neither does a USB disk (its raw image takes no snapshot).
So a module that goes online (r4s-ebpf-datapath D11) or plugs in the data disk
(r4s-services D10) takes the router from its snapshot once, as ``module_router``,
and keeps it for all of its tests; a test puts back what it changed. At the end
of the module the disks come out and the router returns to its snapshot.
"""

import functools
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

import pytest

from wrt_tests import app
from wrt_tests.datapath import Online, dae_start
from wrt_tests.emu import SOURCE_FILE, Emulator
from wrt_tests.internet import REGISTRY
from wrt_tests.isp import Isp
from wrt_tests.net import RUNNER_ADDRESS, TOPOLOGY, Network
from wrt_tests.oci import IMAGE, TAG, extract_root, image_layout, push
from wrt_tests.poll import until
from wrt_tests.router import Router
from wrt_tests.storage import Disk, initialize, wait_mounted

UPGRADE_IMAGE = "targets/*-sysupgrade.tar.gz"
# The test CA, where the router's Go programs (podman, tailscale) find it.
CA_ON_ROUTER = "/etc/ssl/certs/wrt-test-ca.crt"

if TYPE_CHECKING:
    from collections.abc import Iterator

    from labgrid import Target


@pytest.fixture(scope="session")
def emulation_dir() -> Path:
    """Return the directory emu-prepare made from the image under test (scripts/test.sh)."""
    return Path(os.environ["LG_EMU_DIR"])


@pytest.fixture(scope="session")
def network(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Network]:
    """Build the sandbox topology around the emulator."""
    with Network(TOPOLOGY, tmp_path_factory.mktemp("net")) as sandbox:
        yield sandbox


@pytest.fixture(scope="session")
def isp(network: Network) -> Isp:
    """Return the handle on the emulated ISP's sessions."""
    return Isp(network["isp"], network.workdir / "isp")


@pytest.fixture(scope="session")
def emulator(
    target: Target,
    network: Network,
    emulation_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Emulator]:
    """Boot the emulated R4S from a fresh overlay of the shipped disk inside ``network``."""
    del network  # requested for its taps, which the emulator joins
    console_log = tmp_path_factory.mktemp("emulator") / "console.log"
    machine = Emulator(target, emulation_dir, console_log)
    machine.reset_disk()
    machine.power_on()
    yield machine
    machine.power_cut()


@pytest.fixture(scope="session")
def booted_router(target: Target, emulator: Emulator) -> Router:
    """Wait for the router to finish booting, then snapshot the emulator."""
    router = Router(target, emulator)
    router.wait_ready()
    router.disconnect()
    emulator.save()
    return router


@pytest.fixture
def router(booted_router: Router) -> Iterator[Router]:
    """Provide the router in its post-boot state; the emulator returns to it afterwards."""
    yield booted_router
    booted_router.reset()


@pytest.fixture(scope="module")
def module_router(booted_router: Router) -> Iterator[Router]:
    """Provide the router from its post-boot state for a whole module; return to it after."""
    booted_router.reset()
    yield booted_router
    booted_router.reset()


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
def data_disk(
    module_router: Router, emulator: Emulator, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Disk]:
    """Plug in a blank disk on port 1 and make it the data disk (``wrt-data init``)."""
    disk = Disk.blank(emulator, tmp_path_factory.mktemp("disks"), "data")
    disk.plug(1)
    try:
        assert initialize(module_router, disk) == 0  # noqa: S101
        wait_mounted(module_router)
        yield disk
    finally:
        disk.unplug()


@pytest.fixture(scope="session")
def app_image(
    network: Network, emulation_dir: Path, tmp_path_factory: pytest.TempPathFactory
) -> str:
    """Push the test app image to the emulated internet's registry; return its reference."""
    work = tmp_path_factory.mktemp("oci")
    layout = image_layout(extract_root(emulation_dir / "disk.raw", work / "root"), work / "layout")
    reference = f"{REGISTRY[0]}/{IMAGE}:{TAG}"
    push(network["inet"], layout, TAG, reference, network.workdir)
    return reference


@pytest.fixture(scope="module")
def trusted_ca(internet_zone: Online) -> Online:
    """Have the router resolve and trust the emulated internet's servers (test CA)."""
    internet_zone.router.put(internet_zone.network.workdir / "pki" / "ca.crt", CA_ON_ROUTER)
    return internet_zone


@pytest.fixture(scope="module")
def app_pod(trusted_ca: Online, data_disk: Disk, app_image: str) -> Online:
    """Declare the app Pod on the data disk and wait until wrt-containers has started it."""
    del data_disk  # requested for the Pod's place
    app.declare(trusted_ca.router, app_image)
    app.wait_running(trusted_ca.router)
    return trusted_ca


@pytest.fixture(scope="session")
def emulation_source(emulation_dir: Path) -> dict[str, str]:
    """Return what emu-prepare recorded about the emulator's files."""
    path = emulation_dir / SOURCE_FILE
    return cast("dict[str, str]", json.loads(path.read_text()))


@pytest.fixture(scope="session")
def build_output(emulation_source: dict[str, str]) -> Path:
    """Return the output directory of the build the emulator boots."""
    return Path(emulation_source["build"])


@pytest.fixture(scope="session")
def upgrade_image(build_output: Path) -> Path:
    """Return the single-slot upgrade image of the build under test."""
    (image,) = build_output.glob(UPGRADE_IMAGE)
    return image


class _QuietHandler(SimpleHTTPRequestHandler):
    @override
    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output free of access logs."""


@pytest.fixture(scope="session")
def repository(build_output: Path, network: Network) -> Iterator[str]:
    """Serve the build's packages on the runner's LAN address; yield the base URL."""
    del network  # requested for the runner's LAN address
    handler = functools.partial(_QuietHandler, directory=str(build_output))
    with ThreadingHTTPServer((RUNNER_ADDRESS, 0), handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://{RUNNER_ADDRESS}:{server.server_address[1]}"
        server.shutdown()
