"""build/upstream-pinning: every patch states its upstream status, with write-ups in step.

And a patch series gives the same commit whatever the git configuration of the
user who applies it (wrt_tests.model.series, as patch.sh applies it).
"""

import os
from typing import TYPE_CHECKING

from wrt_tests import spec
from wrt_tests.model.patches import (
    DOC,
    repository_patches,
    unstated,
    without_patch,
    without_write_up,
    write_ups,
)
from wrt_tests.model.series import Series

if TYPE_CHECKING:
    from pathlib import Path

CAPABILITY = "build/upstream-pinning"
REQUIREMENT = "Every patch states its upstream status"
# A user's git configuration: it fixes whitespace on apply, signs every commit
# with a signing program that fails, and converts line endings on checkout.
USER_CONFIGURATION = """[apply]
whitespace = fix
[commit]
gpgSign = true
[gpg]
program = false
[core]
autocrlf = true
"""


@spec(CAPABILITY, REQUIREMENT, "Patch without a status")
def test_every_patch_states_its_status() -> None:
    patches = repository_patches()
    assert patches
    assert unstated(patches) == []


@spec(CAPABILITY, REQUIREMENT, "Patch meant for upstream without a write-up")
def test_patches_meant_for_upstream_have_their_write_ups() -> None:
    assert without_write_up(repository_patches(), write_ups(DOC.read_text())) == []


@spec(CAPABILITY, REQUIREMENT, "Write-up without a patch")
def test_every_write_up_names_its_patch() -> None:
    assert without_patch(repository_patches(), write_ups(DOC.read_text())) == []


@spec(CAPABILITY, "Ordered patches, stop on failure", "A git configuration of the user's own")
def test_the_series_commit_ignores_the_user_s_git_configuration(tmp_path: Path) -> None:
    series = Series(tmp_path)
    # A third patch, whose line ends in a blank: whitespace that apply would fix.
    (series.repo / "c.txt").write_text("c\none\ntwo, patched \n")
    series.git("commit", "-q", "-a", "-m", "patch c")
    series.git("format-patch", "-q", "-1", "--start-number", "3", "-o", str(series.patches))
    series.git("checkout", "-q", "--detach", series.base)
    without = series.apply({**os.environ, "GIT_CONFIG_GLOBAL": os.devnull})
    assert without.returncode == 0, without.stderr
    head = series.head
    files = {path.name: path.read_bytes() for path in series.files()}
    configuration = tmp_path / "gitconfig"
    configuration.write_text(USER_CONFIGURATION)
    own = series.apply({**os.environ, "GIT_CONFIG_GLOBAL": str(configuration)})
    assert own.returncode == 0, own.stderr
    assert series.head == head
    assert {path.name: path.read_bytes() for path in series.files()} == files
