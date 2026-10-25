"""quality/undefined-behavior: undefined behavior is fixed in the code, not masked."""

from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.device.ubsan import PROBE, PROFILE, Traps, report
from wrt_tests.model.shell import library
from wrt_tests.model.undefined_behavior import load_register, load_report, stale, unreviewed

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.device.router import Router
    from wrt_tests.model.boards import Board
    from wrt_tests.model.outputs import Manifest

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


@spec(CAPABILITY, REVIEWED, "Package packed again without a compile")
def test_a_package_packed_again_keeps_its_warnings(tmp_path: Path) -> None:
    # OpenWrt rewrites a package's log whenever it runs its compile step: with
    # nothing but the packing's lines when it packs the package again (its apk
    # gone from the output directory, or its packaging rules changed), and with
    # make's time line alone when it finds it up to date. The build's time log
    # names neither as compiled; a host build of the package is a stage of its
    # own (host-compile), whose log is another.
    logs, records = tmp_path / "logs", tmp_path / "records"
    for name, log in {
        "packed": "rstrip.sh: ipkg-aarch64_generic/packed/usr/bin/packed: executable\n"
        "time: package/packed/compile#6.54#0.74#95.63\n",
        "idle": "time: package/idle/compile#0.07#0.02#0.16\n",
        "hosted": "rstrip.sh: ipkg-aarch64_generic/hosted/usr/bin/hosted: executable\n",
    }.items():
        (logs / "package" / name).mkdir(parents=True)
        (logs / "package" / name / "compile.txt").write_text(log)
        record = records / "package" / name / "compile.tsv"
        record.parent.mkdir(parents=True)
        record.write_text(f"-Wuninitialized\t{name}.c\t\t3\n")
    (tmp_path / "time.tsv").write_text(
        "1700000000.0\tbegin\tcompile\ttarget/linux\n1700000001.0\tend\tcompile\ttarget/linux\n"
        "1700000002.0\tbegin\thost-compile\tpackage/hosted\n"
        "1700000003.0\tend\thost-compile\tpackage/hosted\n"
    )

    result = library(
        "warnings", 'warnings_harvest "$@"', str(logs), str(records), "time.tsv", cwd=tmp_path
    )

    assert result.returncode == 0, result.stderr
    for name in ("packed", "idle", "hosted"):
        record = records / "package" / name / "compile.tsv"
        assert record.read_text() == f"-Wuninitialized\t{name}.c\t\t3\n"


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
