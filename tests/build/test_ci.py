"""build/ci: a build hands on its image and kmods with a manifest that describes them."""

import json
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from wrt_tests import spec
from wrt_tests.boards import load
from wrt_tests.emu import MANIFEST_FILE, sha256

if TYPE_CHECKING:
    from wrt_tests.router import Router

CAPABILITY = "build/ci"
REPO = Path(__file__).resolve().parents[2]
IMAGES = ("targets/*-factory.img.gz", "targets/*-sysupgrade.tar.gz")
KMODS = "targets/packages/packages.adb"


@spec(CAPABILITY, "Image and kmods from the same build", "Complete manifest")
def test_the_manifest_describes_the_build(router: Router, build_output: Path) -> None:
    manifest = cast("dict[str, Any]", json.loads((build_output / MANIFEST_FILE).read_text()))
    files = manifest["files"]
    assert manifest["run"]
    assert manifest["upstream_lock_sha256"] == sha256(REPO / "upstream.lock")
    # It names the board the images were built for, and its device, after which
    # OpenWrt names them.
    device = load(manifest["board"]).device
    assert manifest["device"] == device
    images = [path for pattern in IMAGES for path in build_output.glob(pattern)]
    assert len(images) == len(IMAGES)
    for image in images:
        assert f"-{device}-" in image.name
        assert files[image.relative_to(build_output).as_posix()] == sha256(image)
    assert files[KMODS] == sha256(build_output / KMODS)
    # Its vermagic is the one of the image's kernel and of every kmod.
    vermagic = f"~{manifest['vermagic']}-"
    assert vermagic in router.run("apk list -I kernel")
    index = subprocess.run(
        ["apk", "adbdump", build_output / KMODS], capture_output=True, text=True, check=True
    ).stdout
    kernels = set(re.findall(r"kernel=([^\s\"']+)", index))
    assert kernels
    assert all(vermagic in kernel for kernel in kernels), kernels
