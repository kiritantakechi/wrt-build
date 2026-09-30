"""release/publishing: one signed build, assembled into a release that says where it came from.

scripts/release-publish.sh assembles the session's signed build (conftest); its
upload is judged by what it hands to gh, a stand-in on PATH that records its
arguments. The workflow checks read .github/workflows/build.yml.
"""

import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml

from wrt_tests import spec

if TYPE_CHECKING:
    from collections.abc import Sequence

CAPABILITY = "release/publishing"
REPO = Path(__file__).resolve().parents[2]
PUBLISH = REPO / "scripts" / "release-publish.sh"
BUILD = REPO / ".github" / "workflows" / "build.yml"
LOCK = REPO / "upstream.lock"
FACTORY = "-factory.img.gz"
UPGRADE = "-sysupgrade.tar.gz"
KMODS = "targets/packages/packages.adb"


def _publish(
    signed: Path, release: Path, *options: str, gh: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run release-publish.sh; with ``gh``, the stand-in's directory goes first on PATH."""
    environment = dict(os.environ)
    if gh is not None:
        environment["PATH"] = f"{gh}{os.pathsep}{environment['PATH']}"
    return subprocess.run(
        [PUBLISH, signed, release, *options],
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
def test_release_contents(signed_repo: Path, tmp_path: Path) -> None:
    release = tmp_path / "release"
    assert _publish(signed_repo, release).returncode == 0
    info = json.loads((release / "release.json").read_text())
    assets = set(info["assets"])
    assert {"repo.tar", "manifest.json", "manifest.json.sig", "SHA256SUMS"} <= assets
    assert any(name.endswith(FACTORY) for name in assets)
    assert any(name.endswith(UPGRADE) for name in assets)
    sums = subprocess.run(
        ["sha256sum", "--check", "SHA256SUMS"], cwd=release, capture_output=True, check=False
    )
    assert sums.returncode == 0
    # The kmods in the repository depend on the kernel the manifest names.
    manifest = json.loads((release / "manifest.json").read_text())
    with tarfile.open(release / "repo.tar") as repo:
        repo.extract(KMODS, tmp_path / "repo", filter="data")
    index = subprocess.run(
        ["apk", "adbdump", tmp_path / "repo" / KMODS], capture_output=True, text=True, check=True
    ).stdout
    kernels = set(re.findall(r"kernel=([^\s\"']+)", index))
    assert kernels
    assert all(manifest["vermagic"] in kernel for kernel in kernels), kernels


@spec(CAPABILITY, "Publish after signing and drill", "Upgrade drill fails")
def test_nothing_is_published_without_the_drill() -> None:
    jobs = cast("dict[str, Any]", yaml.safe_load(BUILD.read_text()))["jobs"]
    # publish runs only after upgrade-drill succeeded (no always() or failure()).
    assert jobs["publish"]["needs"] == "upgrade-drill"
    assert "if" not in jobs["publish"]
    assert jobs["upgrade-drill"]["needs"] == "sign"
    assert "--upload" in jobs["publish"]["steps"][-1]["run"]


@spec(CAPABILITY, "Candidates and stable releases", "PR build")
def test_a_bump_is_a_candidate(signed_repo: Path, tmp_path: Path, gh: Path) -> None:
    release = tmp_path / "release"
    result = _publish(signed_repo, release, "--prerelease", "--upload", gh=gh)
    assert result.returncode == 0, result.stderr
    assert json.loads((release / "release.json").read_text())["prerelease"] is True
    args = _gh_args(gh)
    assert args[:2] == ["release", "create"]
    assert {"--prerelease", "--latest=false"} <= set(args)
    # Only main's build is published as stable: a bump branch's is a candidate.
    publish = yaml.safe_load(BUILD.read_text())["jobs"]["publish"]["steps"][-1]
    assert publish["env"]["CANDIDATE"] == (
        "${{ github.ref != 'refs/heads/main' && '--prerelease' || '' }}"
    )


@spec(CAPABILITY, "Candidates and stable releases", "Post-merge build")
def test_main_is_a_stable_release(signed_repo: Path, tmp_path: Path, gh: Path) -> None:
    release = tmp_path / "release"
    result = _publish(signed_repo, release, "--upload", gh=gh)
    assert result.returncode == 0, result.stderr
    assert json.loads((release / "release.json").read_text())["prerelease"] is False
    args = _gh_args(gh)
    assert "--latest" in args
    assert "--prerelease" not in args
    uploaded = {Path(arg).name for arg in args if arg.startswith(str(release))}
    assert "repo.tar" in uploaded
    assert "release.json" not in uploaded


@spec(CAPABILITY, "Artifacts come from one build", "Artifacts mixed from two builds")
def test_two_builds_are_not_mixed(signed_repo: Path, tmp_path: Path, gh: Path) -> None:
    mixed = tmp_path / "mixed"
    shutil.copytree(signed_repo, mixed)
    (upgrade,) = (mixed / "targets").glob(f"*{UPGRADE}")
    with upgrade.open("ab") as image:
        image.write(b"another build")
    result = _publish(mixed, tmp_path / "release", "--upload", gh=gh)
    assert result.returncode != 0
    assert "not all from the build" in result.stderr
    assert not (tmp_path / "release").exists()
    assert not (gh / "gh.args").exists()


@spec(CAPABILITY, "Traceable release notes", "View release notes")
def test_release_notes_name_the_sources(signed_repo: Path, tmp_path: Path) -> None:
    release = tmp_path / "release"
    assert _publish(signed_repo, release).returncode == 0
    notes = json.loads((release / "release.json").read_text())["notes"]
    for line in LOCK.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            assert line.split()[2] in notes
    patches = json.loads((signed_repo / "manifest.json").read_text())["patches_sha256"]
    assert patches in notes
