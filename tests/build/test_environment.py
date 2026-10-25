"""build/environment: entry points refuse macOS, stop at a failed step, patch what changed.

And they pass their arguments on as given.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from wrt_tests import spec
from wrt_tests.model.boards import load_all
from wrt_tests.model.series import Series

CAPABILITY = "build/environment"
REPO = Path(__file__).resolve().parents[2]
SOURCE_ENTRY_POINTS = ("fetch", "patch", "config", "download", "build", "toolchain-build")


@pytest.fixture
def macos(tmp_path: Path) -> dict[str, str]:
    """Return an environment whose uname reports Darwin, like a macOS host."""
    uname = shutil.which("uname")
    assert uname is not None
    shim = tmp_path / "bin" / "uname"
    shim.parent.mkdir()
    shim.write_text(f'#!/bin/sh\n[ "$1" = -s ] && echo Darwin || exec {uname} "$@"\n')
    shim.chmod(0o755)
    return {**os.environ, "PATH": f"{shim.parent}:{os.environ['PATH']}"}


@spec(CAPABILITY, "Build only on Linux hosts", "Run directly on macOS")
@pytest.mark.parametrize("entry_point", SOURCE_ENTRY_POINTS)
def test_macos_is_refused(entry_point: str, macos: dict[str, str], tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    result = subprocess.run(
        [str(REPO / "scripts" / f"{entry_point}.sh")],
        env={**macos, "WRT_WORKDIR": str(workdir)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "only on Linux" in result.stderr
    assert list(workdir.iterdir()) == []


@spec(CAPABILITY, "Common build entry points", "Substep fails")
def test_failed_step_stops_the_build(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "work"
    not_a_directory.write_text("")
    result = subprocess.run(
        ["just", "--justfile", str(REPO / "justfile"), "build", load_all()[0].id, "dev"],
        env={**os.environ, "WRT_WORKDIR": str(not_a_directory)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "scripts/fetch.sh" in result.stderr
    assert "scripts/patch.sh" not in result.stderr
    assert "scripts/build.sh" not in result.stderr


@spec(CAPABILITY, "Common build entry points", "An argument with a blank or a quote")
@pytest.mark.parametrize("shape", ["a command after a blank", "a quote"])
def test_an_argument_reaches_its_script_whole(tmp_path: Path, shape: str) -> None:
    justfile = REPO / "justfile"
    # No recipe pastes an argument into its command line: just passes them on.
    dump = subprocess.run(
        ["just", "--justfile", justfile, "--dump", "--dump-format", "json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    recipes = json.loads(dump)["recipes"]
    pasted = [
        name
        for name, recipe in recipes.items()
        for line in recipe["body"]
        if any(not isinstance(fragment, str) for fragment in line)
    ]
    assert pasted == []
    # A board's name with more after it reaches boards.sh as one argument.
    ran = tmp_path / "ran"
    board = load_all()[0].id
    argument = f"{board}; touch {ran}" if shape == "a command after a blank" else f"{board}'s"
    result = subprocess.run(
        ["just", "--justfile", justfile, "boards", argument],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert f"no board '{argument}'" in result.stderr
    assert not ran.exists()


@pytest.fixture
def series(tmp_path: Path) -> Series:
    """Return a scratch repository with its series applied once."""
    created = Series(tmp_path)
    applied = created.apply()
    assert applied.returncode == 0, applied.stderr
    return created


@spec(CAPABILITY, "Rebuild only what changed", "Re-apply an unchanged series")
def test_reapplied_series_writes_nothing(series: Series) -> None:
    head = series.head
    # Ignored build output stays, time included; an untracked file of no commit goes.
    (series.repo / "po2lmo.o").write_bytes(b"built")
    (series.repo / "stray.patch").write_text("a patch a package would apply\n")
    before = series.age()
    applied = series.apply()
    assert applied.returncode == 0, applied.stderr
    assert series.head == head
    assert series.times() == {name: time for name, time in before.items() if name != "stray.patch"}


@spec(CAPABILITY, "Rebuild only what changed", "Change one patch")
def test_changed_patch_rewrites_its_files_only(series: Series) -> None:
    before = series.age()
    patch = series.patch(2)
    # The second patch changes b.txt another way and no longer adds d.txt.
    head, *diffs = (
        patch.read_text().replace("+two, patched", "+two, patched again").split("\ndiff --git ")
    )
    kept = [diff for diff in diffs if not diff.startswith("a/d.txt ")]
    patch.write_text("\ndiff --git ".join([head, *kept]).rstrip("\n") + "\n")
    applied = series.apply()
    assert applied.returncode == 0, applied.stderr
    after = series.times()
    assert {name for name in before if after.get(name) != before[name]} == {"b.txt", "d.txt"}
    assert "d.txt" not in after
    assert (series.repo / "b.txt").read_text().endswith("two, patched again\n")


@spec(CAPABILITY, "Rebuild only what changed", "A patch that does not apply")
def test_failing_patch_leaves_the_tree(series: Series) -> None:
    head = series.head
    before = series.age()
    patch = series.patch(2)
    patch.write_text(patch.read_text().replace(" one\n", " uno\n"))
    applied = series.apply()
    assert applied.returncode != 0
    assert patch.name in applied.stderr
    assert series.head == head
    assert series.times() == before
