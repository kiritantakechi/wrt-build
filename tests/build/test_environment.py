"""build/environment: entry points refuse macOS, stop at a failed step, patch what changed."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from wrt_tests import spec
from wrt_tests.boards import load_all

CAPABILITY = "build/environment"
REPO = Path(__file__).resolve().parents[2]
SOURCE_ENTRY_POINTS = ("fetch", "patch", "config", "build", "toolchain-build")
LIB = REPO / "scripts" / "lib.sh"
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@localhost",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@localhost",
}
# A time no file of a fresh checkout has: a file git writes again gets a new one.
OLD = 1_000_000_000 * 1_000_000_000


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


class Series:
    """A scratch repository and a series of two patches, applied as patch.sh does."""

    def __init__(self, root: Path) -> None:
        """Create the repository under ``root``, its base commit and the two patches.

        The first patch changes a.txt; the second changes b.txt and adds d.txt.
        """
        self.repo = root / "repo"
        self.patches = root / "patches"
        self.repo.mkdir()
        self._git("init", "-q")
        (self.repo / ".gitignore").write_text("*.o\n")
        for name in ("a", "b", "c"):
            (self.repo / f"{name}.txt").write_text(f"{name}\none\ntwo\n")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "base")
        self.base = self._git("rev-parse", "HEAD")
        (self.repo / "a.txt").write_text("a\none\ntwo, patched\n")
        self._git("commit", "-q", "-a", "-m", "patch a")
        (self.repo / "b.txt").write_text("b\none\ntwo, patched\n")
        (self.repo / "d.txt").write_text("d\n")
        self._git("add", "d.txt")
        self._git("commit", "-q", "-a", "-m", "patch b")
        self._git("format-patch", "-q", "-2", "-o", str(self.patches))
        self._git("checkout", "-q", "--detach", self.base)

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            env={**os.environ, **GIT_IDENTITY},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    @property
    def head(self) -> str:
        """Return the commit the work tree is on."""
        return self._git("rev-parse", "HEAD")

    def patch(self, number: int) -> Path:
        """Return the series' patch with ``number``."""
        (found,) = self.patches.glob(f"{number:04}-*.patch")
        return found

    def apply(self) -> subprocess.CompletedProcess[str]:
        """Build the series' commit on the base and move the work tree to it."""
        return subprocess.run(
            [
                "sh",
                "-c",
                f'. "{LIB}" && commit=$(series_commit "$1" "$2" "$3") && move_tree "$2" "$commit"',
                "sh",
                str(self.patches),
                str(self.repo),
                self.base,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def files(self) -> list[Path]:
        """Return the files of the work tree, untracked ones included."""
        return [path for path in self.repo.iterdir() if path.is_file()]

    def age(self) -> dict[str, int]:
        """Give every file of the work tree an old time; return the times."""
        for path in self.files():
            os.utime(path, ns=(OLD, OLD))
        return self.times()

    def times(self) -> dict[str, int]:
        """Return each file's modification time."""
        return {path.name: path.stat().st_mtime_ns for path in self.files()}


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
