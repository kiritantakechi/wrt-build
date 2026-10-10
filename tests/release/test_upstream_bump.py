"""release/upstream-bump: the weekly bump of upstream.lock, merged only after the upgrade drill.

scripts/upstream-bump.sh runs against local repositories standing in for the
three upstreams; scripts/patch.sh against one the patch queue does not apply to.
The drill tests (marked drill) are what CI's upgrade-drill job runs with the
production keys and the latest stable release as the base; here, and in
system-test, they run with the session's keys and this build as the base.
"""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.boards import load_all
from wrt_tests.data import read_json, write_json
from wrt_tests.outputs import MANIFEST_FILE, Manifest

if TYPE_CHECKING:
    from wrt_tests.boards import Board
    from wrt_tests.datapath import Online
    from wrt_tests.drill import Drill

CAPABILITY = "release/upstream-bump"
REPO = Path(__file__).resolve().parents[2]
NAMES = ("openwrt", "packages", "luci")
BBR_PATCH = "patches/openwrt/0001-generic-6.18-add-TCP-BBRv3.patch"
DRILL_BASE = REPO / "scripts" / "drill-base.sh"
# A stand-in for gh: the latest release is latest.json beside it, or GitHub's
# error in latest.error, and the release's assets are the files in assets/.
GH = """#!/bin/sh
here=$(dirname "$0")
case "$1" in
    api)
        [ -f "$here/latest.json" ] && exec cat "$here/latest.json"
        cat "$here/latest.error" >&2
        exit 1
        ;;
    release)
        shift 3
        while [ "$#" -gt 0 ]; do
            case "$1" in
                --pattern) pattern=$2 ;;
                --dir) dir=$2 ;;
            esac
            shift 2
        done
        found=
        for asset in "$here"/assets/$pattern; do
            [ -e "$asset" ] && cp "$asset" "$dir/" && found=1
        done
        [ -n "$found" ] || { echo "no assets match the file pattern" >&2; exit 1; }
        ;;
esac
"""
NOT_FOUND = "gh: Not Found (HTTP 404)"
# The CI runs of the stand-in builds: the released one, and this one.
RELEASED = "37000000001-1"
THIS_BUILD = "37000000002-1"
TAG = "r20260930-23fd10a-7"
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
    # A tree as fetch leaves it: the pinned commit checked out.
    work = tmp_path / "work"
    tree = work / "openwrt"
    _git(tmp_path, "clone", "-q", str(openwrt), str(tree))
    _git(tree, "checkout", "-q", "--detach", heads["openwrt"])
    (tree / "feeds.conf").touch()
    result = subprocess.run(
        [repository / "scripts" / "patch.sh"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **GIT_IDENTITY, "WRT_WORKDIR": str(work)},
    )
    assert result.returncode != 0
    assert f"patch does not apply: {BBR_PATCH}" in result.stderr


def _factory(board: Board, *, suffix: str = "") -> str:
    return f"openwrt-rockchip-armv8-{board.device}{suffix}-erofs-factory.img.gz"


def _manifest(board: Board, run: str, files: dict[str, str]) -> Manifest:
    """Return the manifest of a build of ``board`` by CI run ``run``, listing ``files``."""
    return Manifest.model_validate(
        {
            "board": board.id,
            "device": board.device,
            "run": run,
            "profile": "ci",
            "build": board.id,
            "cflags": "-O3",
            "kernel_cflags": "-O2",
            "toolchain_cflags": "-O3",
            "upstream_lock_sha256": "0" * 64,
            "patches_sha256": "0" * 64,
            "openwrt_head": "0" * 40,
            "kernel_version": "",
            "vermagic": "",
            "files": files,
        }
    )


def _drill_base(
    root: Path, board: Board, latest: str | None, error: str = NOT_FOUND
) -> subprocess.CompletedProcess[str]:
    """Run drill-base.sh for ``board`` beside this build's stand-in outputs, in ``root``.

    ``latest`` is the latest release's tag, with its assets in ``root/gh/assets``,
    or None when GitHub answers the lookup with ``error``: by default, that there
    is no stable release.
    """
    ci = root / "work" / "out" / board.id / "ci"
    (ci / "targets").mkdir(parents=True)
    write_json(ci / MANIFEST_FILE, _manifest(board, THIS_BUILD, {}))
    (ci / "targets" / _factory(board)).write_bytes(b"this build's factory image")
    (ci / "u-boot-qemu.bin").write_bytes(b"this build's emulator firmware")
    gh = root / "gh"
    (gh / "assets").mkdir(parents=True, exist_ok=True)
    (gh / "gh").write_text(GH)
    (gh / "gh").chmod(0o755)
    if latest is None:
        (gh / "latest.error").write_text(error)
    else:
        assets = [{"name": path.name} for path in sorted((gh / "assets").iterdir())]
        (gh / "latest.json").write_text(json.dumps({"tag_name": latest, "assets": assets}))
    return subprocess.run(
        [DRILL_BASE, board.id],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{gh}{os.pathsep}{os.environ['PATH']}",
            "WRT_WORKDIR": str(root / "work"),
        },
    )


def _release(root: Path, board: Board, image: bytes, *, listed: bytes | None = None) -> None:
    """Put the board's set in the stand-in's release: its manifest and factory image.

    The manifest lists ``listed`` (``image`` unless given) as the factory image. A
    longer device name's image beside it must not be taken for the board's.
    """
    assets = root / "gh" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / _factory(board)).write_bytes(image)
    (assets / _factory(board, suffix="-enterprise")).write_bytes(b"another device's image")
    digest = hashlib.sha256(image if listed is None else listed).hexdigest()
    files = {f"targets/{_factory(board)}": digest}
    write_json(assets / f"{board.device}-{MANIFEST_FILE}", _manifest(board, RELEASED, files))


def _base(root: Path, board: Board) -> tuple[str, bytes]:
    """Return what the drill starts from: the run that built its image, and the image.

    Its manifest is that build's, its profile drill-base, its files the image and
    this build's emulator firmware, as emu-prepare checks them.
    """
    base = root / "work" / "out" / board.id / "drill-base"
    (image,) = (base / "targets").iterdir()
    assert image.name == _factory(board)
    manifest = read_json(base / MANIFEST_FILE, Manifest)
    assert manifest.profile == "drill-base"
    assert manifest.files == {
        f"targets/{image.name}": hashlib.sha256(image.read_bytes()).hexdigest(),
        "u-boot-qemu.bin": hashlib.sha256(b"this build's emulator firmware").hexdigest(),
    }
    return manifest.run, image.read_bytes()


@spec(CAPABILITY, "Merge only after the upgrade drill passes", "Drill base of each board")
def test_each_drill_starts_from_the_board_s_latest_release(tmp_path: Path) -> None:
    board, other = load_all()[:2]
    _release(tmp_path, board, b"the released factory image")
    result = _drill_base(tmp_path, board, TAG)
    assert result.returncode == 0, result.stderr
    assert f"drill base: {TAG}, the latest stable release" in result.stderr
    assert _base(tmp_path, board) == (RELEASED, b"the released factory image")
    # A board that no stable release carries yet starts from this build...
    result = _drill_base(tmp_path, other, TAG)
    assert result.returncode == 0, result.stderr
    assert f"carries no {other.id}" in result.stderr
    assert _base(tmp_path, other) == (THIS_BUILD, b"this build's factory image")
    # ...as every board does before the first release.
    first = tmp_path / "first"
    result = _drill_base(first, board, None)
    assert result.returncode == 0, result.stderr
    assert "no stable release yet" in result.stderr
    assert _base(first, board) == (THIS_BUILD, b"this build's factory image")


@spec(CAPABILITY, "Merge only after the upgrade drill passes", "Drill base cannot be had")
@pytest.mark.parametrize("failure", ["lookup", "image"])
def test_a_drill_base_that_cannot_be_had_stops_the_drill(failure: str, tmp_path: Path) -> None:
    board = load_all()[0]
    if failure == "lookup":
        result = _drill_base(tmp_path, board, None, error="gh: Server Error (HTTP 502)")
        refusal = "cannot look up the latest release"
    else:
        _release(tmp_path, board, b"a changed factory image", listed=b"the released one")
        result = _drill_base(tmp_path, board, TAG)
        refusal = f"of {TAG} does not match {board.device}-manifest.json"
    assert result.returncode != 0
    assert refusal in result.stderr, result.stderr
    assert not (tmp_path / "work" / "out" / board.id / "drill-base" / MANIFEST_FILE).exists()


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
