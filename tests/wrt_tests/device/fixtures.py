"""The fixtures of the emulated board and its router (module-boundaries D6).

The session boots the shipped image once and snapshots it; every test that uses
``router`` starts from that snapshot.

A PPP session does not survive a jump back to the snapshot (the ISP would still
hold the old one), and neither does a USB disk (its raw image takes no snapshot).
So a module that goes online (r4s-ebpf-datapath D11) or plugs in the data disk
(r4s-services D10) takes the router from its snapshot once, as ``module_router``,
and keeps it for all of its tests; a test puts back what it changed. At the end
of the module the disks come out and the router returns to its snapshot.

In a ubsan build (toolchain-o3 D5), the kernel log is read for traps before the
snapshot erases it: after the boot, after every test that used the router, and
when a module ends.
"""

import subprocess
from typing import TYPE_CHECKING, cast

import pytest

from wrt_tests.device.emu import Emulator
from wrt_tests.device.router import Router
from wrt_tests.device.storage import Disk, initialize, wait_mounted
from wrt_tests.device.trust import trust_keys
from wrt_tests.device.ubsan import PROFILE as UBSAN
from wrt_tests.device.ubsan import Traps, report

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from labgrid import Target

    from wrt_tests.model.keys import Keys
    from wrt_tests.sandbox.net import Network


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
