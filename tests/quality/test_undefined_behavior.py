"""quality/undefined-behavior: undefined behavior is fixed in the code, not masked."""

from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.emu import manifest_flags
from wrt_tests.undefined_behavior import load_register, load_report, stale, unreviewed

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.boards import Board

CAPABILITY = "quality/undefined-behavior"
REVIEWED = "UB-indicative warnings fixed or reviewed"
# The options that define away a class of undefined behavior instead of fixing it.
MASKING = frozenset(
    {
        "-fwrapv",
        "-fno-strict-overflow",
        "-fno-strict-aliasing",
        "-fno-delete-null-pointer-checks",
        "-fno-aggressive-loop-optimizations",
    }
)


@spec(CAPABILITY, REVIEWED, "Unreviewed warning")
def test_every_warning_is_fixed_or_reviewed(board: Board, build_output: Path) -> None:
    found = unreviewed(load_report(build_output), load_register(), board.id)
    assert not found, "UB-indicative warnings no review covers:\n" + "\n".join(map(str, found))


@spec(CAPABILITY, REVIEWED, "Stale review")
def test_every_review_matches_a_warning(board: Board, build_output: Path) -> None:
    found = stale(load_register(), load_report(build_output), board.id)
    assert not found, "reviews that match no warning of the build:\n" + "\n".join(map(str, found))


@spec(CAPABILITY, "No global masking of undefined behavior", "Check the shared flags")
@pytest.mark.parametrize("key", ["cflags", "kernel_cflags"])
def test_no_shared_flag_masks_undefined_behavior(key: str, build_output: Path) -> None:
    # The flags every target package compiles with, and those the build adds to the
    # kernel's own; a package's build may add such an option for itself.
    assert not MASKING & set(manifest_flags(build_output, key))
