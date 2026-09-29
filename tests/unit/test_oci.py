"""Unit tests of wrt_tests.oci: the test app image from the firmware's own programs."""

import gzip
import io
import json
import tarfile
from typing import TYPE_CHECKING

import pytest

from wrt_tests.internet import REGISTRY
from wrt_tests.oci import IMAGE, PROGRAMS, TAG, extract_root, image_layout, needed, push

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.net import Network


@pytest.fixture(scope="module")
def root(emulation_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return extract_root(emulation_dir / "disk.raw", tmp_path_factory.mktemp("oci") / "root")


@pytest.fixture(scope="module")
def layout(root: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return image_layout(root, tmp_path_factory.mktemp("oci") / "layout")


def test_needed_libraries(root: Path) -> None:
    assert "libc.so" in needed((root / "bin/busybox").read_bytes())
    uhttpd = needed((root / "usr/sbin/uhttpd").read_bytes())
    assert "libc.so" in uhttpd
    assert any(library.startswith("libubox.so") for library in uhttpd)


def test_layer_holds_the_programs_and_their_libraries(layout: Path) -> None:
    index = json.loads((layout / "index.json").read_text())
    blobs = layout / "blobs" / "sha256"
    manifest = json.loads((blobs / index["manifests"][0]["digest"].split(":")[1]).read_bytes())
    layer = gzip.decompress((blobs / manifest["layers"][0]["digest"].split(":")[1]).read_bytes())
    with tarfile.open(fileobj=io.BytesIO(layer)) as tar:
        names = set(tar.getnames())
        assert tar.getmember("lib/ld-musl-aarch64.so.1").linkname == "libc.so"
    assert {*PROGRAMS, "lib/libc.so", "bin/sh", "bin/nc", "www"} <= names
    assert any(name.startswith("lib/libubox.so") for name in names)


def test_image_is_arm64(layout: Path, network: Network) -> None:
    inspected = json.loads(network["inet"].run("skopeo", "inspect", f"oci:{layout}:{TAG}"))
    assert (inspected["Architecture"], inspected["Os"]) == ("arm64", "linux")
    assert len(inspected["Layers"]) == 1


def test_image_goes_to_the_registry(layout: Path, network: Network) -> None:
    reference = f"{REGISTRY[0]}/{IMAGE}-unit:{TAG}"
    push(network["inet"], layout, TAG, reference, network.workdir)
    trust = network.workdir / "pki" / "trust"
    inspected = network["inet"].run(
        "skopeo", "inspect", f"--cert-dir={trust}", f"docker://{reference}"
    )
    assert json.loads(inspected)["Architecture"] == "arm64"
