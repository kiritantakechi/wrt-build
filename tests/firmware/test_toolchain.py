"""firmware/toolchain: optimization comes from configuration, not from build system patches."""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from wrt_tests import spec
from wrt_tests.emu import MANIFEST_FILE

if TYPE_CHECKING:
    from wrt_tests.boards import Board

CAPABILITY = "firmware/toolchain"
PATCHES = Path(__file__).resolve().parents[2] / "patches" / "openwrt"
OPTIMIZATION = re.compile(r"-O([0-3gsz]|fast)?")


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
def test_packages_compile_for_the_board(board: Board, build_output: Path) -> None:
    # Every target package compiles with TARGET_CFLAGS, which the manifest records;
    # of several -O and -mcpu flags, GCC takes the last.
    flags = json.loads((build_output / MANIFEST_FILE).read_text())["cflags"].split()
    size = flags.index("-Os")
    optimizations = [i for i, flag in enumerate(flags) if OPTIMIZATION.fullmatch(flag)]
    cpus = [i for i, flag in enumerate(flags) if flag.startswith("-mcpu=")]
    assert flags[optimizations[-1]] == "-O2"
    assert flags[cpus[-1]] == f"-mcpu={board.cpu}"
    assert size < optimizations[-1]
    assert size < cpus[-1]
