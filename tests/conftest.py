"""Fixtures of every system test: the sandbox network, the emulator and the router.

On the emulator the session boots the shipped image once, snapshots it, and every
test that uses ``router`` starts from that snapshot. On the device the same
fixtures only wait for the router; ``network`` and ``emulator`` are None.
"""

import functools
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

import pytest

from wrt_tests.emu import SOURCE_FILE, Emulator
from wrt_tests.net import RUNNER_ADDRESS, TOPOLOGY, Network
from wrt_tests.router import Router

if TYPE_CHECKING:
    from collections.abc import Iterator

    from labgrid import Target

    from wrt_tests.markers import TargetKind


@pytest.fixture(scope="session")
def target_kind(pytestconfig: pytest.Config) -> TargetKind:
    """Return the kind of target this run is against."""
    return cast("TargetKind", pytestconfig.getoption("--target-kind"))


@pytest.fixture(scope="session")
def network(
    target_kind: TargetKind, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Network | None]:
    """Build the sandbox topology around the emulator; None on the device."""
    if target_kind != "emulation":
        yield None
        return
    with Network(TOPOLOGY, tmp_path_factory.mktemp("net")) as sandbox:
        yield sandbox


@pytest.fixture(scope="session")
def emulator(
    target: Target, network: Network | None, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Emulator | None]:
    """Boot the emulated R4S from a fresh overlay of the shipped disk; None on the device."""
    if network is None:
        yield None
        return
    console_log = tmp_path_factory.mktemp("emulator") / "console.log"
    machine = Emulator(target, Path(os.environ["LG_EMU_DIR"]), console_log)
    machine.reset_disk()
    machine.power_on()
    yield machine
    machine.power_cut()


@pytest.fixture(scope="session")
def booted_router(target: Target, emulator: Emulator | None) -> Router:
    """Wait for the router to finish booting, then snapshot the emulator."""
    router = Router(target, emulator)
    router.wait_ready()
    if emulator is not None:
        router.disconnect()
        emulator.save()
    return router


@pytest.fixture
def router(booted_router: Router) -> Iterator[Router]:
    """Provide the router in its post-boot state; the emulator returns to it afterwards."""
    yield booted_router
    booted_router.reset()


@pytest.fixture(scope="session")
def emulation_source() -> dict[str, str]:
    """Return what emu-prepare recorded about the emulator's files."""
    path = Path(os.environ["LG_EMU_DIR"]) / SOURCE_FILE
    return cast("dict[str, str]", json.loads(path.read_text()))


@pytest.fixture(scope="session")
def build_output(emulation_source: dict[str, str]) -> Path:
    """Return the output directory of the build the emulator boots."""
    return Path(emulation_source["manifest"]).parent


class _QuietHandler(SimpleHTTPRequestHandler):
    @override
    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output free of access logs."""


@pytest.fixture(scope="session")
def repository(build_output: Path, network: Network) -> Iterator[str]:
    """Serve the build's packages on the runner's LAN address; yield the base URL."""
    if network is None:
        msg = "the repository is served inside the emulator's network sandbox"
        raise RuntimeError(msg)
    handler = functools.partial(_QuietHandler, directory=str(build_output))
    with ThreadingHTTPServer((RUNNER_ADDRESS, 0), handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://{RUNNER_ADDRESS}:{server.server_address[1]}"
        server.shutdown()
