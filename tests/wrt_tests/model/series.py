"""A scratch repository and a series of patches, applied as patch.sh applies a patch queue."""

import os
import subprocess
from typing import TYPE_CHECKING

from wrt_tests.model.shell import library

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@localhost",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@localhost",
}
# A time no file of a fresh checkout has: a file git writes again gets a new one.
OLD = 1_000_000_000 * 1_000_000_000


class Series:
    """A scratch repository and a series of two patches, applied as patch.sh does."""

    def __init__(self, root: Path) -> None:
        """Create the repository under ``root``, its base commit and the two patches.

        The first patch changes a.txt; the second changes b.txt and adds d.txt.
        """
        self.repo = root / "repo"
        self.patches = root / "patches"
        self.repo.mkdir()
        self.git("init", "-q")
        (self.repo / ".gitignore").write_text("*.o\n")
        for name in ("a", "b", "c"):
            (self.repo / f"{name}.txt").write_text(f"{name}\none\ntwo\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD")
        (self.repo / "a.txt").write_text("a\none\ntwo, patched\n")
        self.git("commit", "-q", "-a", "-m", "patch a")
        (self.repo / "b.txt").write_text("b\none\ntwo, patched\n")
        (self.repo / "d.txt").write_text("d\n")
        self.git("add", "d.txt")
        self.git("commit", "-q", "-a", "-m", "patch b")
        self.git("format-patch", "-q", "-2", "-o", str(self.patches))
        self.git("checkout", "-q", "--detach", self.base)

    def git(self, *args: str) -> str:
        """Run git in the repository, as the test's identity and its configuration alone."""
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            env={**os.environ, **GIT_IDENTITY, "GIT_CONFIG_GLOBAL": os.devnull},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    @property
    def head(self) -> str:
        """Return the commit the work tree is on."""
        return self.git("rev-parse", "HEAD")

    def patch(self, number: int) -> Path:
        """Return the series' patch with ``number``."""
        (found,) = self.patches.glob(f"{number:04}-*.patch")
        return found

    def apply(self, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        """Build the series' commit on the base and move the work tree to it, in ``env``."""
        return library(
            "tree upstream",
            'commit=$(series_commit "$1" "$2" "$3") && move_tree "$2" "${commit}"',
            str(self.patches),
            str(self.repo),
            self.base,
            env=env,
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
