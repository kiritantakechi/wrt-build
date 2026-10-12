"""build/ci: a build hands on its image and kmods with a manifest that describes them.

And main's runs delete the caches of the branches merged into main.
"""

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from wrt_tests import spec
from wrt_tests.device.emu import sha256
from wrt_tests.model.boards import load
from wrt_tests.model.github import MAIN, Repository, run_script

if TYPE_CHECKING:
    from wrt_tests.device.router import Router
    from wrt_tests.model.outputs import Manifest

CAPABILITY = "build/ci"
REPO = Path(__file__).resolve().parents[2]
IMAGES = ("targets/*-factory.img.gz", "targets/*-sysupgrade.tar.gz")
KMODS = "targets/packages/packages.adb"


@spec(CAPABILITY, "Image and kmods from the same build", "Complete manifest")
def test_the_manifest_describes_the_build(
    router: Router, build_output: Path, manifest: Manifest
) -> None:
    files = manifest.files
    assert manifest.run
    assert manifest.upstream_lock_sha256 == sha256(REPO / "upstream.lock")
    # It names the board the images were built for, and its device, after which
    # OpenWrt names them.
    device = load(manifest.board).device
    assert manifest.device == device
    images = [path for pattern in IMAGES for path in build_output.glob(pattern)]
    assert len(images) == len(IMAGES)
    for image in images:
        assert f"-{device}-" in image.name
        assert files[image.relative_to(build_output).as_posix()] == sha256(image)
    assert files[KMODS] == sha256(build_output / KMODS)
    # Its vermagic is the one of the image's kernel and of every kmod.
    vermagic = f"~{manifest.vermagic}-"
    assert vermagic in router.run("apk list -I kernel")
    index = subprocess.run(
        ["apk", "adbdump", build_output / KMODS], capture_output=True, text=True, check=True
    ).stdout
    kernels = set(re.findall(r"kernel=([^\s\"']+)", index))
    assert kernels
    assert all(vermagic in kernel for kernel in kernels), kernels


@spec(CAPABILITY, "Main's caches kept whole", "A merged branch")
def test_main_deletes_merged_branches_caches(tmp_path: Path) -> None:
    compare = {
        "merged": "behind",
        "identical": "identical",
        "ahead": "ahead",
        "diverged": "diverged",
    }
    repository = Repository(branches=["main", *compare], compare=compare)
    for branch in (*compare, "deleted"):
        repository.cache(f"refs/heads/{branch}", f"dl-{branch}")
    repository.cache("refs/pull/1/merge", "dl-pull")
    repository.cache(MAIN, "toolchain-1")
    # The caches job of main's run (scripts/cache-prune.sh).
    result, left = run_script(tmp_path, repository, "cache-prune.sh", "toolchain-1", ref=MAIN)
    assert result.returncode == 0, result.stderr
    # A branch merged into main, or one deleted, keeps no cache; the others stay.
    assert sorted(ref for ref, _ in left) == [
        "refs/heads/ahead",
        "refs/heads/diverged",
        MAIN,
        "refs/pull/1/merge",
    ]
