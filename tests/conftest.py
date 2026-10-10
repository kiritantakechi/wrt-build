"""Fixtures of every system test: the sandbox network, the emulator and the router.

The session boots the shipped image once and snapshots it; every test that uses
``router`` starts from that snapshot.

A PPP session does not survive a jump back to the snapshot (the ISP would still
hold the old one), and neither does a USB disk (its raw image takes no snapshot).
So a module that goes online (r4s-ebpf-datapath D11) or plugs in the data disk
(r4s-services D10) takes the router from its snapshot once, as ``module_router``,
and keeps it for all of its tests; a test puts back what it changed. At the end
of the module the disks come out and the router returns to its snapshot.

The session signs the build under test with release keys of its own (the
script CI signs releases with) and its router trusts those keys instead of the
image's, as a release image trusts the release keys: upgrades and packages are
the build's, signed. The upgrade drill (r4s-release-pipeline D5) instead names
the production-signed candidate in $WRT_SIGNED; then nothing is signed here
and the image's own trust anchors decide.
"""

import functools
import os
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

import pytest

from wrt_tests.device.emu import Emulator
from wrt_tests.device.router import Router
from wrt_tests.device.storage import Disk, initialize, wait_mounted
from wrt_tests.device.trust import trust_ca, trust_keys
from wrt_tests.device.ubsan import PROFILE as UBSAN
from wrt_tests.device.ubsan import Traps, report
from wrt_tests.model import boards
from wrt_tests.model.data import read_json
from wrt_tests.model.keys import Keys, sign
from wrt_tests.model.outputs import MANIFEST_FILE, SOURCE_FILE, EmulationSource, Manifest
from wrt_tests.model.poll import until
from wrt_tests.sandbox.internet import REGISTRY
from wrt_tests.sandbox.isp import Isp
from wrt_tests.sandbox.net import RUNNER_ADDRESS, Network, topology
from wrt_tests.sandbox.oci import IMAGE, TAG, extract_root, image_layout, push
from wrt_tests.services import app
from wrt_tests.services.datapath import Online, dae_start

UPGRADE_IMAGE = "targets/*-sysupgrade.tar.gz"
SIGNED_ENV = "WRT_SIGNED"

if TYPE_CHECKING:
    from collections.abc import Iterator

    from labgrid import Target


@pytest.fixture(scope="session")
def emulation_dir() -> Path:
    """Return the directory emu-prepare made from the image under test (scripts/test.sh)."""
    return Path(os.environ["LG_EMU_DIR"])


@pytest.fixture(scope="session")
def network(board: boards.Board, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Network]:
    """Build the sandbox topology around the emulated board."""
    with Network(topology(board), tmp_path_factory.mktemp("net")) as sandbox:
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
    """Boot the emulated board from a fresh overlay of the shipped disk inside ``network``."""
    del network  # requested for its taps, which the emulator joins
    console_log = tmp_path_factory.mktemp("emulator") / "console.log"
    machine = Emulator(target, emulation_dir, console_log)
    machine.reset_disk()
    machine.power_on()
    yield machine
    machine.power_cut()


@pytest.fixture(scope="session")
def harness_key(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return the key the harness logs in to the router with (its public half next to it)."""
    key = tmp_path_factory.mktemp("ssh") / "harness"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "wrt-build tests", "-f", key],
        check=True,
    )
    return key


@pytest.fixture(scope="session")
def booted_router(
    target: Target, emulator: Emulator, release_keys: Keys | None, harness_key: Path
) -> Router:
    """Wait for the router to finish booting, then snapshot it, trusting the session's keys.

    The harness's key is authorized as well, for when root has a password.
    """
    router = Router(target, emulator, harness_key)
    router.wait_ready()
    router.put(harness_key.with_suffix(".pub"), "/etc/dropbear/authorized_keys")
    if release_keys is not None:
        trust_keys(router, release_keys)
    router.disconnect()
    emulator.save()
    return router


@pytest.fixture(scope="session")
def ubsan_traps(booted_router: Router, profile: str) -> Traps | None:
    """Return the watch on the traps of undefined behavior in a ubsan build, else None.

    A trap while the router booted fails every test that uses the router.
    """
    if profile != UBSAN:
        return None
    traps = Traps(booted_router)
    report(traps.new(), "while the router booted")
    return traps


@pytest.fixture
def router(booted_router: Router, ubsan_traps: Traps | None) -> Iterator[Router]:
    """Provide the router in its post-boot state; the emulator returns to it afterwards.

    In a ubsan build, a trap during the test fails it: the kernel log is read
    before the snapshot erases it.
    """
    yield booted_router
    try:
        if ubsan_traps is not None:
            report(ubsan_traps.new(), "during the test")
    finally:
        booted_router.reset()


@pytest.fixture(scope="module")
def module_router(booted_router: Router, ubsan_traps: Traps | None) -> Iterator[Router]:
    """Provide the router from its post-boot state for a whole module; return to it after.

    In a ubsan build, check_module_traps fails each test after which something
    trapped; a trap outside the tests, in a module fixture, fails the module's
    last test, read before the snapshot erases it.
    """
    booted_router.reset()
    yield booted_router
    try:
        if ubsan_traps is not None:
            report(ubsan_traps.new(), "outside the module's tests")
    finally:
        booted_router.reset()


@pytest.fixture(autouse=True)
def check_module_traps(request: pytest.FixtureRequest) -> Iterator[None]:
    """In a ubsan build, fail a test of a module that keeps the router if anything trapped."""
    yield
    if "module_router" in request.fixturenames:
        traps = cast("Traps | None", request.getfixturevalue("ubsan_traps"))
        if traps is not None:
            report(traps.new(), "during the test")


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
    trust_ca(internet_zone.router, internet_zone.network.workdir)
    return internet_zone


@pytest.fixture(scope="module")
def app_pod(trusted_ca: Online, data_disk: Disk, app_image: str) -> Online:
    """Declare the app Pod on the data disk and wait until wrt-containers has started it."""
    del data_disk  # requested for the Pod's place
    app.declare(trusted_ca.router, app_image)
    app.wait_running(trusted_ca.router)
    return trusted_ca


@pytest.fixture(scope="session")
def emulation_source(emulation_dir: Path) -> EmulationSource:
    """Return what emu-prepare recorded about the emulator's files."""
    return read_json(emulation_dir / SOURCE_FILE, EmulationSource)


@pytest.fixture(scope="session")
def build_output(emulation_source: EmulationSource) -> Path:
    """Return the output directory of the build the emulator boots."""
    return emulation_source.build


@pytest.fixture(scope="session")
def manifest(build_output: Path) -> Manifest:
    """Return the manifest of the build under test."""
    return read_json(build_output / MANIFEST_FILE, Manifest)


@pytest.fixture(scope="session")
def board(manifest: Manifest) -> boards.Board:
    """Return the board the build under test was built for, as its manifest names it."""
    return boards.load(manifest.board)


@pytest.fixture(scope="session")
def profile(manifest: Manifest) -> str:
    """Return the profile the build under test was built in, as its manifest names it."""
    return manifest.profile


@pytest.fixture(scope="session")
def release_keys(tmp_path_factory: pytest.TempPathFactory) -> Keys | None:
    """Return the session's release keys, or None when $WRT_SIGNED names a signed build."""
    if os.environ.get(SIGNED_ENV):
        return None
    return Keys.make(tmp_path_factory.mktemp("keys"))


@pytest.fixture(scope="session")
def signed_repo(
    build_output: Path, release_keys: Keys | None, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Return the build under test signed with the session's keys (or $WRT_SIGNED)."""
    if release_keys is None:
        return Path(os.environ[SIGNED_ENV])
    return sign(build_output, tmp_path_factory.mktemp("signed") / "build", release_keys)


@pytest.fixture(scope="session")
def signed_boards(
    board: boards.Board, signed_repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Return the signed builds as the sign job hands them on: this board's, named after it."""
    directory = tmp_path_factory.mktemp("boards")
    (directory / board.id).symlink_to(signed_repo)
    return directory


@pytest.fixture(scope="session")
def upgrade_image(signed_repo: Path) -> Path:
    """Return the signed single-slot upgrade image of the build under test."""
    (image,) = signed_repo.glob(UPGRADE_IMAGE)
    return image


class _QuietHandler(SimpleHTTPRequestHandler):
    @override
    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output free of access logs."""


@pytest.fixture(scope="session")
def repository(signed_repo: Path, network: Network) -> Iterator[str]:
    """Serve the build's signed packages on the runner's LAN address; yield the base URL."""
    del network  # requested for the runner's LAN address
    handler = functools.partial(_QuietHandler, directory=str(signed_repo))
    with ThreadingHTTPServer((RUNNER_ADDRESS, 0), handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://{RUNNER_ADDRESS}:{server.server_address[1]}"
        server.shutdown()
