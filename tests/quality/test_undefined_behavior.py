"""quality/undefined-behavior: undefined behavior is fixed in the code, not masked."""

from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.ubsan import PROBE, PROFILE, Traps, report
from wrt_tests.undefined_behavior import load_register, load_report, stale, unreviewed

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.boards import Board
    from wrt_tests.outputs import Manifest
    from wrt_tests.router import Router

CAPABILITY = "quality/undefined-behavior"
REVIEWED = "UB-indicative warnings fixed or reviewed"
# The register reviews the builds that ship; UBSan's instrumentation changes what
# GCC warns of.
NOT_SHIPPED = "a ubsan build ships nothing; the register reviews the builds that do"
# The shell's status of a command killed by SIGTRAP.
TRAPPED = 128 + 5
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
def test_every_warning_is_fixed_or_reviewed(board: Board, build_output: Path, profile: str) -> None:
    if profile == PROFILE:
        pytest.skip(NOT_SHIPPED)
    found = unreviewed(load_report(build_output), load_register(), board.id)
    assert not found, "UB-indicative warnings no review covers:\n" + "\n".join(map(str, found))


@spec(CAPABILITY, REVIEWED, "Stale review")
def test_every_review_matches_a_warning(board: Board, build_output: Path, profile: str) -> None:
    if profile == PROFILE:
        pytest.skip(NOT_SHIPPED)
    found = stale(load_register(), load_report(build_output), board.id)
    assert not found, "reviews that match no warning of the build:\n" + "\n".join(map(str, found))


@spec(CAPABILITY, "No global masking of undefined behavior", "Check the shared flags")
@pytest.mark.parametrize("key", ["cflags", "kernel_cflags"])
def test_no_shared_flag_masks_undefined_behavior(key: str, manifest: Manifest) -> None:
    # The flags every target package compiles with, and those the build adds to the
    # kernel's own; a package's build may add such an option for itself.
    assert not MASKING & set(getattr(manifest, key))


@spec(CAPABILITY, "Undefined behavior traps under UBSan", "Trap during a system test")
def test_a_trap_fails_the_test_and_names_the_process(
    router: Router, ubsan_traps: Traps | None
) -> None:
    # The probe overflows a signed integer; the harness reads the trap from the
    # kernel log, as the router fixture does after every test, and fails with it.
    if ubsan_traps is None:
        pytest.skip("only a ubsan build traps")
    # Run alone, the probe would be the session itself, whose death by a signal
    # the SSH client reports as 255; the shell reports 128 + the signal instead.
    assert router.returncode(f"{PROBE}; exit $?") == TRAPPED
    with pytest.raises(pytest.fail.Exception, match=rf"{PROBE}\[[0-9]+\] at pc [0-9a-f]+"):
        report(ubsan_traps.new(), "during the test")
