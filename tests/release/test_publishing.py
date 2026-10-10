"""release/publishing: the boards' signed builds, assembled into a release that names its sources.

scripts/release-publish.sh assembles the session's signed build (conftest), as
the sign job hands it on (board-model D10); its upload is judged by what it hands
to gh, a stand-in on PATH that records its arguments. The workflow checks read
.github/workflows/build.yml.
"""

import os
import re
import subprocess
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml

from wrt_tests import spec
from wrt_tests.model.boards import load_all
from wrt_tests.model.data import read_json, write_json
from wrt_tests.model.outputs import MANIFEST_FILE, RELEASE_FILE, Manifest, Release
from wrt_tests.model.trees import linked_copy, replace

if TYPE_CHECKING:
    from collections.abc import Sequence

    from wrt_tests.model.boards import Board

CAPABILITY = "release/publishing"
REPO = Path(__file__).resolve().parents[2]
PUBLISH = REPO / "scripts" / "release-publish.sh"
BUILD = REPO / ".github" / "workflows" / "build.yml"
LOCK = REPO / "upstream.lock"
FACTORY = "-factory.img.gz"
UPGRADE = "-sysupgrade.tar.gz"
KMODS = "targets/packages/packages.adb"


def _publish(
    signed: Path, release: Path, *options: str, gh: Path | None = None, every_board: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run release-publish.sh on the boards ``signed`` holds, or on every board.

    ``every_board`` leaves ``--boards`` out, for the script's default of every
    board; with ``gh``, the stand-in's directory goes first on PATH.
    """
    environment = dict(os.environ)
    if gh is not None:
        environment["PATH"] = f"{gh}{os.pathsep}{environment['PATH']}"
    held = ",".join(sorted(path.name for path in signed.iterdir()))
    boards = () if every_board else ("--boards", held)
    return subprocess.run(
        [PUBLISH, signed, release, *boards, *options],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


@pytest.fixture
def gh(tmp_path: Path) -> Path:
    """Return a directory with a gh that records its arguments in gh.args."""
    directory = tmp_path / "bin"
    directory.mkdir()
    script = directory / "gh"
    script.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >"{directory}/gh.args"\n')
    script.chmod(0o755)
    return directory


def _gh_args(gh: Path) -> Sequence[str]:
    return (gh / "gh.args").read_text().splitlines()


@spec(CAPABILITY, "Publish after signing and drill", "Inspect Release contents")
def test_release_contents(board: Board, signed_boards: Path, tmp_path: Path) -> None:
    release = tmp_path / "release"
    assert _publish(signed_boards, release).returncode == 0
    info = read_json(release / RELEASE_FILE, Release)
    assert info.boards == (board.id,)
    # Each board's set is named after its device.
    device = board.device
    assets = set(info.assets)
    named = {f"{device}-{name}" for name in ("repo.tar", "manifest.json", "manifest.json.sig")}
    assert {*named, "SHA256SUMS"} <= assets
    assert any(f"-{device}-" in name and name.endswith(FACTORY) for name in assets)
    assert any(f"-{device}-" in name and name.endswith(UPGRADE) for name in assets)
    sums = subprocess.run(
        ["sha256sum", "--check", "SHA256SUMS"], cwd=release, capture_output=True, check=False
    )
    assert sums.returncode == 0
    # The kmods in the repository depend on the kernel the manifest names.
    manifest = read_json(release / f"{device}-{MANIFEST_FILE}", Manifest)
    with tarfile.open(release / f"{device}-repo.tar") as repo:
        repo.extract(KMODS, tmp_path / "repo", filter="data")
    index = subprocess.run(
        ["apk", "adbdump", tmp_path / "repo" / KMODS], capture_output=True, text=True, check=True
    ).stdout
    kernels = set(re.findall(r"kernel=([^\s\"']+)", index))
    assert kernels
    assert all(manifest.vermagic in kernel for kernel in kernels), kernels


@spec(CAPABILITY, "Publish after signing and drill", "Upgrade drill fails")
@pytest.mark.parametrize(
    ("results", "passes"),
    [
        (("success", "success", "success"), True),
        # Signing did not run, so neither did any drill: a pull request.
        (("success", "skipped", "skipped"), True),
        (("success", "success", "failure"), False),
        (("success", "success", "cancelled"), False),
        # A failed or rejected signing skips the drills.
        (("success", "failure", "skipped"), False),
        (("failure", "skipped", "skipped"), False),
    ],
)
def test_nothing_is_published_without_the_drill(
    results: tuple[str, str, str], *, passes: bool
) -> None:
    jobs = cast("dict[str, Any]", yaml.safe_load(BUILD.read_text()))["jobs"]
    # publish runs only after every board's drill and the check succeeded (no
    # always() or failure()).
    assert jobs["publish"]["needs"] == ["drill", "upgrade-drill"]
    assert "if" not in jobs["publish"]
    assert "--upload" in jobs["publish"]["steps"][-1]["run"]
    assert "sign" in jobs["drill"]["needs"]
    # The check main's rules require judges the results of the jobs it needs.
    check = jobs["upgrade-drill"]
    assert check["needs"] == ["system-test", "sign", "drill"]
    assert check["if"] == "always()"
    (step,) = check["steps"]
    names = ("SYSTEM_TEST", "SIGN", "DRILL")
    assert list(step["env"]) == list(names)
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", step["run"]],
        env={**os.environ, **dict(zip(names, results, strict=True))},
        capture_output=True,
        check=False,
    )
    assert (result.returncode == 0) == passes


@spec(CAPABILITY, "Candidates and stable releases", "PR build")
def test_a_bump_is_a_candidate(signed_boards: Path, tmp_path: Path, gh: Path) -> None:
    release = tmp_path / "release"
    result = _publish(signed_boards, release, "--prerelease", "--upload", gh=gh)
    assert result.returncode == 0, result.stderr
    assert read_json(release / RELEASE_FILE, Release).prerelease
    args = _gh_args(gh)
    assert args[:2] == ["release", "create"]
    assert {"--prerelease", "--latest=false"} <= set(args)
    # Only main's build is published as stable: a bump branch's is a candidate.
    publish = yaml.safe_load(BUILD.read_text())["jobs"]["publish"]["steps"][-1]
    assert publish["env"]["CANDIDATE"] == (
        "${{ github.ref != 'refs/heads/main' && '--prerelease' || '' }}"
    )


@spec(CAPABILITY, "Candidates and stable releases", "Post-merge build")
def test_main_is_a_stable_release(
    board: Board, signed_boards: Path, tmp_path: Path, gh: Path
) -> None:
    release = tmp_path / "release"
    result = _publish(signed_boards, release, "--upload", gh=gh)
    assert result.returncode == 0, result.stderr
    assert not read_json(release / RELEASE_FILE, Release).prerelease
    args = _gh_args(gh)
    assert "--latest" in args
    assert "--prerelease" not in args
    uploaded = {Path(arg).name for arg in args if arg.startswith(str(release))}
    assert f"{board.device}-repo.tar" in uploaded
    assert RELEASE_FILE not in uploaded


@spec(CAPABILITY, "Publish after signing and drill", "A board missing")
def test_a_release_carries_every_board(
    board: Board, signed_boards: Path, tmp_path: Path, gh: Path
) -> None:
    # The session has this board's build alone, and boards/ describes more.
    others = sorted(other.id for other in load_all() if other.id != board.id)
    assert others
    result = _publish(signed_boards, tmp_path / "release", "--upload", gh=gh, every_board=True)
    assert result.returncode != 0
    asked = " ".join(sorted(other.id for other in load_all()))
    assert f"the release is of {asked}, but {signed_boards} holds the builds of {board.id}" in (
        result.stderr
    )
    assert not (tmp_path / "release").exists()
    assert not (gh / "gh.args").exists()


@spec(CAPABILITY, "Artifacts come from one build", "Artifacts mixed from two builds")
def test_two_builds_are_not_mixed(
    board: Board, signed_repo: Path, tmp_path: Path, gh: Path
) -> None:
    mixed = tmp_path / "mixed"
    linked_copy(signed_repo, mixed / board.id)
    (upgrade,) = (mixed / board.id / "targets").glob(f"*{UPGRADE}")
    replace(upgrade, upgrade.read_bytes() + b"another build")
    result = _publish(mixed, tmp_path / "release", "--upload", gh=gh)
    assert result.returncode != 0
    assert "not all from the build" in result.stderr
    assert not (tmp_path / "release").exists()
    assert not (gh / "gh.args").exists()


@spec(CAPABILITY, "Traceable release notes", "View release notes")
def test_release_notes_name_the_sources(
    signed_repo: Path, signed_boards: Path, tmp_path: Path
) -> None:
    release = tmp_path / "release"
    assert _publish(signed_boards, release).returncode == 0
    notes = read_json(release / RELEASE_FILE, Release).notes
    for line in LOCK.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            assert line.split()[2] in notes
    assert read_json(signed_repo / MANIFEST_FILE, Manifest).patches_sha256 in notes


@spec(CAPABILITY, "Artifacts come from one build", "Boards built from different sources")
@pytest.mark.parametrize("field", ["upstream_lock_sha256", "patches_sha256", "openwrt_head"])
def test_boards_from_different_sources_are_not_mixed(
    board: Board, signed_repo: Path, tmp_path: Path, gh: Path, field: str
) -> None:
    # Beside the build under test, a build of another board from other sources:
    # a copy of it, whose manifest names that board and another source.
    other = next(other for other in load_all() if other.id != board.id)
    signed = tmp_path / "signed"
    signed.mkdir()
    (signed / board.id).symlink_to(signed_repo)
    linked_copy(signed_repo, signed / other.id)
    manifest = signed / other.id / MANIFEST_FILE
    content = read_json(manifest, Manifest)
    source = "0" * len(getattr(content, field))
    built = {"board": other.id, "device": other.device, field: source}
    write_json(manifest, content.model_copy(update=built))
    result = _publish(signed, tmp_path / "release", "--upload", gh=gh)
    assert result.returncode != 0
    assert f"were built from different sources: their {field} differs" in result.stderr
    assert not (tmp_path / "release").exists()
    assert not (gh / "gh.args").exists()
