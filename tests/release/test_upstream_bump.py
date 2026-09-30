"""release/upstream-bump: the weekly bump of upstream.lock, merged only after the upgrade drill.

scripts/upstream-bump.sh runs against local repositories standing in for the
three upstreams; scripts/patch.sh against one the patch queue does not apply to.
The drill tests (marked drill) are what CI's upgrade-drill job runs with the
production keys and the latest stable release as the base; here, and in
system-test, they run with the session's keys and this build as the base.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec

if TYPE_CHECKING:
    from wrt_tests.datapath import Online
    from wrt_tests.drill import Drill

CAPABILITY = "release/upstream-bump"
REPO = Path(__file__).resolve().parents[2]
NAMES = ("openwrt", "packages", "luci")
BBR_PATCH = "patches/openwrt/0001-generic-6.18-add-TCP-BBRv3.patch"
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "upstream",
    "GIT_AUTHOR_EMAIL": "upstream@example.net",
    "GIT_COMMITTER_NAME": "upstream",
    "GIT_COMMITTER_EMAIL": "upstream@example.net",
}


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", repository, *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **GIT_IDENTITY},
    ).stdout.strip()


def _commit(repository: Path, message: str) -> str:
    """Add one commit to a working repository; return its SHA."""
    (repository / "log").open("a").write(f"{message}\n")
    _git(repository, "add", "log")
    _git(repository, "commit", "-q", "-m", message)
    return _git(repository, "rev-parse", "HEAD")


def _write_lock(tmp_path: Path, lock: Path, pinned: dict[str, str]) -> None:
    """Write a lock of the upstreams in ``tmp_path`` that pins their ``pinned`` commits."""
    lines = []
    for name in NAMES:
        repository = tmp_path / name
        epoch = _git(repository, "log", "-1", "--format=%ct", pinned[name])
        lines.append(f"{name} {repository} {pinned[name]} {epoch}")
    lock.write_text("# the upstreams\n" + "\n".join(lines) + "\n")


def _upstreams(tmp_path: Path, commits: int) -> tuple[Path, dict[str, str]]:
    """Make the three upstreams with ``commits`` commits each; return a lock of their first."""
    first = {}
    for name in NAMES:
        repository = tmp_path / name
        repository.mkdir()
        _git(repository, "init", "-q", "-b", "main")
        first[name] = _commit(repository, f"{name} 1")
        for number in range(2, commits + 1):
            _commit(repository, f"{name} {number}")
    lock = tmp_path / "upstream.lock"
    _write_lock(tmp_path, lock, first)
    return lock, first


def _bump(lock: Path, description: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [REPO / "scripts" / "upstream-bump.sh", description, "--lock", lock],
        capture_output=True,
        text=True,
        check=False,
    )


@spec(CAPABILITY, "Weekly automated PR", "Upstream has updates")
def test_updates_make_a_pull_request(tmp_path: Path) -> None:
    lock, first = _upstreams(tmp_path, commits=3)
    description = tmp_path / "pull-request.md"
    assert _bump(lock, description).returncode == 0
    title, _, *body = description.read_text().splitlines()
    assert title.startswith("upstream: bump openwrt packages luci")
    text = "\n".join(body)
    for name in NAMES:
        head = _git(tmp_path / name, "rev-parse", "HEAD")
        assert f"| {name} | `{first[name]}` | `{head}` |" in text
        assert f"{head[:7]} {name} 3" in text
        entry = next(
            line.split() for line in lock.read_text().splitlines() if line.startswith(name)
        )
        assert entry[2:] == [head, _git(tmp_path / name, "log", "-1", "--format=%ct")]


@spec(CAPABILITY, "Weekly automated PR", "Upstream has no updates")
def test_no_updates_make_nothing(tmp_path: Path) -> None:
    lock, _ = _upstreams(tmp_path, commits=1)
    before = lock.read_text()
    description = tmp_path / "pull-request.md"
    result = _bump(lock, description)
    assert result.returncode == 0
    assert "has not moved" in result.stderr
    assert not description.exists()
    assert lock.read_text() == before


@spec(CAPABILITY, "Fail clearly when patches do not apply", "BBRv3 patch conflict")
def test_a_patch_that_does_not_apply_is_named(tmp_path: Path) -> None:
    # openwrt took a BBR patch of its own, under the name ours adds; a copy of
    # this repository pins that commit.
    _upstreams(tmp_path, commits=1)
    openwrt = tmp_path / "openwrt"
    taken = openwrt / next(
        line.removeprefix("+++ b/")
        for line in (REPO / BBR_PATCH).read_text().splitlines()
        if line.startswith("+++ b/")
    )
    taken.parent.mkdir(parents=True)
    taken.write_text("upstream's own\n")
    _git(openwrt, "add", ".")
    _git(openwrt, "commit", "-q", "-m", "generic: BBRv3")
    repository = tmp_path / "repository"
    for part in ("scripts", "patches"):
        shutil.copytree(REPO / part, repository / part)
    heads = {name: _git(tmp_path / name, "rev-parse", "HEAD") for name in NAMES}
    _write_lock(tmp_path, repository / "upstream.lock", heads)
    work = tmp_path / "work"
    (work / "openwrt").mkdir(parents=True)
    (work / "openwrt" / "feeds.conf").touch()
    result = subprocess.run(
        [repository / "scripts" / "patch.sh"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **GIT_IDENTITY, "WRT_WORKDIR": str(work)},
    )
    assert result.returncode != 0
    assert f"patch does not apply: {BBR_PATCH}" in result.stderr


@pytest.mark.drill
@spec(CAPABILITY, "Merge only after the upgrade drill passes", "Drill passes")
def test_the_drill_passes(drill: Drill) -> None:
    outcome = drill.run()
    assert outcome.confirmed, outcome
    assert outcome.slot != outcome.base_slot
    assert drill.configuration_kept(), json.dumps(drill.pushed)


@pytest.mark.drill
@spec(CAPABILITY, "Merge only after the upgrade drill passes", "Candidate fails the health check")
def test_a_failing_candidate_fails_the_drill(drill: Drill, online: Online) -> None:
    del online  # the router the drill runs on
    drill.register_failing_check()
    outcome = drill.run()
    assert not outcome.confirmed
    assert outcome.slot == outcome.base_slot  # rolled back
