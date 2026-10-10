"""Unit tests of wrt_tests.sandbox.releases: the Releases API stand-in on the emulated internet."""

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from wrt_tests.model.data import write_json
from wrt_tests.model.outputs import RELEASE_FILE, Release
from wrt_tests.sandbox import releases
from wrt_tests.sandbox.internet import RELEASES

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.sandbox.net import Network

REPOSITORY = "owner/repository"
API = f"https://{RELEASES[0]}/repos/{REPOSITORY}"


def _release(directory: Path, tag: str, *, prerelease: bool) -> Path:
    """Write a release of one asset, as release-publish.sh lays one out."""
    directory.mkdir(parents=True)
    (directory / "asset.bin").write_bytes(tag.encode() * 4096)
    info = Release(tag=tag, prerelease=prerelease, notes=tag, boards=(), assets=("asset.bin",))
    write_json(directory / RELEASE_FILE, info)
    return directory


def _curl(network: Network, url: str, *options: str) -> subprocess.CompletedProcess[bytes]:
    ca = network.workdir / "pki" / "ca.crt"
    return subprocess.run(
        network["inet"].argv("curl", "--silent", "--cacert", str(ca), *options, url),
        capture_output=True,
        check=False,
    )


@pytest.fixture(scope="module")
def published(network: Network, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Publish a stable release, then a newer candidate."""
    work = tmp_path_factory.mktemp("releases")
    root = network.workdir / releases.ROOT
    releases.publish(root, REPOSITORY, _release(work / "stable", "r1", prerelease=False))
    releases.publish(root, REPOSITORY, _release(work / "candidate", "r2", prerelease=True))
    # Another repository's releases are its own.
    releases.publish(root, "owner/other", _release(work / "other", "r3", prerelease=False))
    return root


def test_latest_is_the_newest_stable_release(network: Network, published: Path) -> None:
    del published
    latest = json.loads(_curl(network, f"{API}/releases/latest").stdout)
    assert latest["tag_name"] == "r1"
    listed = json.loads(_curl(network, f"{API}/releases").stdout)
    assert [release["tag_name"] for release in listed] == ["r2", "r1"]
    assert listed[0]["prerelease"]


def test_assets_download_whole_or_cut(network: Network, published: Path) -> None:
    latest = json.loads(_curl(network, f"{API}/releases/latest").stdout)
    url = latest["assets"][0]["browser_download_url"]
    assert url == f"https://{RELEASES[0]}/{REPOSITORY}/releases/download/r1/asset.bin"
    assert _curl(network, url).stdout == (published / REPOSITORY / "r1" / "asset.bin").read_bytes()
    releases.cut(published, REPOSITORY, "r1", 1000)
    try:
        cut = _curl(network, url)
        assert cut.returncode != 0
        assert len(cut.stdout) == 1000  # noqa: PLR2004
    finally:
        releases.cut(published, REPOSITORY, "r1", None)
