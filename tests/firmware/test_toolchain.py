"""firmware/toolchain: optimization comes from configuration, not from build system patches."""

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec

if TYPE_CHECKING:
    from collections.abc import Sequence

    from wrt_tests.boards import Board
    from wrt_tests.outputs import Manifest

CAPABILITY = "firmware/toolchain"
PATCHES = Path(__file__).resolve().parents[2] / "patches" / "openwrt"
OPTIMIZATION = re.compile(r"-O([0-3gsz]|fast)?")
MCPU = re.compile(r"-mcpu=.+")
# The options that relax IEEE floating-point semantics (toolchain-o3 D2).
RELAXING = frozenset(
    {
        "-Ofast",
        "-ffast-math",
        "-funsafe-math-optimizations",
        "-ffinite-math-only",
        "-fno-signed-zeros",
        "-fno-trapping-math",
        "-fassociative-math",
    }
)


def _last(flags: Sequence[str], pattern: re.Pattern[str]) -> int:
    """Return the index of the last of ``flags`` that ``pattern`` matches; GCC takes that one."""
    return max(i for i, flag in enumerate(flags) if pattern.fullmatch(flag))


@spec(CAPABILITY, "Optimization through configuration only", "Audit patch queue")
def test_patch_queue_leaves_target_mk_alone() -> None:
    changed = {
        line.split()[3].removeprefix("b/")
        for patch in PATCHES.glob("*.patch")
        for line in patch.read_text().splitlines()
        if line.startswith("diff --git ")
    }
    assert changed
    assert "include/target.mk" not in changed


@spec(CAPABILITY, "Optimization flags for big.LITTLE cores", "Check compile command")
def test_packages_compile_for_the_board(board: Board, manifest: Manifest) -> None:
    # Every target package compiles with TARGET_CFLAGS, which the manifest records.
    flags = manifest.cflags
    size = flags.index("-Os")
    optimization = _last(flags, OPTIMIZATION)
    cpu = _last(flags, MCPU)
    assert flags[optimization] == "-O3"
    assert flags[cpu] == f"-mcpu={board.cpu}"
    assert size < optimization
    assert size < cpu


@spec(CAPABILITY, "Kernel at its supported optimization level", "Check the kernel's flags")
def test_the_kernel_compiles_for_the_board(board: Board, manifest: Manifest) -> None:
    # Kbuild appends the flags the build adds (KCFLAGS) after its own.
    flags = manifest.kernel_cflags
    assert flags[_last(flags, OPTIMIZATION)] == "-O2"
    assert flags[_last(flags, MCPU)] == f"-mcpu={board.cpu}"


@spec(CAPABILITY, "No relaxed floating-point semantics", "Check for relaxed floating point")
@pytest.mark.parametrize("key", ["cflags", "kernel_cflags"])
def test_no_flag_relaxes_floating_point(key: str, manifest: Manifest) -> None:
    assert not RELAXING & set(getattr(manifest, key))
