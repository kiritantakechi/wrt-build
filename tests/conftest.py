"""Fixtures of every system test: the sandbox network, the emulator and the router.

The session boots the shipped image once and snapshots it; every test that uses
``router`` starts from that snapshot.
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

UPGRADE_IMAGE = "targets/*-sysupgrade.tar.gz"

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
