"""The fixtures of the network around the board (module-boundaries D6).

The sandbox's namespaces and bridges around the emulated board, the emulated
ISP, the test app image in the emulated internet's registry, and the signed
build's package repository on the runner's LAN address.
"""

import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, override

import pytest

from wrt_tests.sandbox.internet import REGISTRY
from wrt_tests.sandbox.isp import Isp
from wrt_tests.sandbox.net import RUNNER_ADDRESS, Network, topology
from wrt_tests.sandbox.oci import IMAGE, TAG, extract_root, image_layout, push

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from wrt_tests.model.boards import Board


class _QuietHandler(SimpleHTTPRequestHandler):
    @override
    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output free of access logs."""


@pytest.fixture(scope="session")
def network(board: Board, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Network]:
    """Build the sandbox topology around the emulated board."""
    with Network(topology(board), tmp_path_factory.mktemp("net")) as sandbox:
        yield sandbox


@pytest.fixture(scope="session")
def isp(network: Network) -> Isp:
    """Return the handle on the emulated ISP's sessions."""
    return Isp(network["isp"], network.workdir / "isp")


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


@pytest.fixture(scope="session")
def repository(signed_repo: Path, network: Network) -> Iterator[str]:
    """Serve the build's signed packages on the runner's LAN address; yield the base URL."""
    del network  # requested for the runner's LAN address
    handler = functools.partial(_QuietHandler, directory=str(signed_repo))
    with ThreadingHTTPServer((RUNNER_ADDRESS, 0), handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://{RUNNER_ADDRESS}:{server.server_address[1]}"
        server.shutdown()
