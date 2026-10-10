"""release/device-sync: the router's local repository of releases, which wrt-sync keeps.

The module's router is online, resolves and trusts the emulated internet, and
runs dae with the test configuration, which routes the Releases stand-in
through the proxy as an administrator routes GitHub. The releases are the
session's signed build, assembled once (release-publish.sh) and published under
a new tag for each release in the stand-in's repository wrt-build/sync, where
wrt-sync is pointed. The test without a data disk comes first: the data disk
comes with the first test that asks for it and stays for the module.
"""

import itertools
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from wrt_tests import releases, spec
from wrt_tests.ab import boot_area_sha256, slot, slot_sha256
from wrt_tests.boards import load_all
from wrt_tests.data import read_json, write_json
from wrt_tests.internet import RELEASES
from wrt_tests.net import DIRECT_TARGET, PROXIED_TARGET, PROXY
from wrt_tests.outputs import RELEASE_FILE, Manifest, Release
from wrt_tests.storage import MOUNT
from wrt_tests.trees import linked_copy, replace

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.boards import Board
    from wrt_tests.datapath import Online
    from wrt_tests.isp import Isp
    from wrt_tests.keys import Keys
    from wrt_tests.router import Router
    from wrt_tests.storage import Disk

CAPABILITY = "release/device-sync"
PUBLISH = Path(__file__).resolve().parents[2] / "scripts" / "release-publish.sh"
REPOSITORY = "wrt-build/sync"
LOCAL = f"{MOUNT}/repo"
UPGRADE = "targets/*-sysupgrade.tar.gz"
# A kmod of the build that the image does not carry, and its module.
KMOD = ("kmod-dummy", "dummy")
KEEP = 3
# Where a cut download stops: well into every asset but the signature.
CUT = 1 << 20
# The byte a tampered image has changed.
TAMPERED = 1 << 20
SYNC_TIMEOUT = 900
# What the router logged around a failed sync: the container's fetch goes through
# podman's network and dae, either of which can refuse it (EPERM).
SYNC_LOG = "logread | grep -E 'wrt-sync|podman|netavark|dae' | tail -n 40"


@dataclass
class Releases:
    """The stand-in's repository wrt-build/sync, and the router that syncs from it."""

    online: Online
    assembled: Path
    root: Path
    runs: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    @property
    def router(self) -> Router:
        """The router that syncs."""
        return self.online.router

    def publish(self, release: Path | None = None, *, prerelease: bool = False) -> str:
        """Publish the build (or ``release``) as a new release, the newest now; return its tag."""
        release = release or self.assembled
        tag = read_json(release / RELEASE_FILE, Release).tag
        return releases.publish(
            self.root,
            REPOSITORY,
            release,
            tag=f"{tag.rsplit('-', 1)[0]}-{next(self.runs)}",
            prerelease=prerelease,
        )

    def sync(self, *options: str) -> tuple[bool, str]:
        """Run wrt-sync; return whether it succeeded and what it said.

        A failed sync's text ends with what the router logged around it.
        """
        output = self.router.run(
            f"wrt-sync {' '.join(options)} 2>&1; echo $?", timeout=SYNC_TIMEOUT
        ).splitlines()
        ok, said = output[-1] == "0", "\n".join(output[:-1])
        if not ok:
            said += f"\n--- the router's log ---\n{self.router.run(SYNC_LOG)}"
        return ok, said

    def current(self) -> str | None:
        """Return the tag of the current release, or None."""
        target = self.router.run(f"readlink {LOCAL}/current || true")
        return target.removeprefix("releases/") or None

    def kept(self) -> list[str]:
        """Return the tags of the releases on the data disk, the latest current first."""
        return self.router.run(f"ls -1t {LOCAL}/releases").split()

    def synced(self) -> str:
        """Return the current release, after syncing a new one if there is none."""
        if (current := self.current()) is not None:
            return current
        tag = self.publish()
        ok, said = self.sync()
        assert ok, said
        return tag


@pytest.fixture(scope="module")
def stand_in(
    dae: Online,
    trusted_ca: Online,
    board: Board,
    signed_boards: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Releases]:
    """Assemble the signed build as a release; point the router's wrt-sync at the stand-in."""
    del trusted_ca  # requested for the router's trust in the stand-in
    assembled = tmp_path_factory.mktemp("sync") / "release"
    subprocess.run(
        [PUBLISH, signed_boards, assembled, "--boards", board.id, "--run", "1"],
        check=True,
        capture_output=True,
    )
    dae.router.run(
        f"uci set wrt-sync.main.api=https://{RELEASES[0]}"
        f" && uci set wrt-sync.main.repository={REPOSITORY} && uci commit wrt-sync"
    )
    root = dae.network.workdir / releases.ROOT
    yield Releases(dae, assembled, root)
    shutil.rmtree(root / REPOSITORY, ignore_errors=True)


@spec(CAPABILITY, "Missing data disk does not affect operation", "No data disk attached")
def test_without_the_data_disk(stand_in: Releases) -> None:
    router = stand_in.router
    assert router.returncode(f"grep -q ' {MOUNT} ' /proc/mounts") != 0, "a data disk is there"
    installed = router.run(f"apk add {KMOD[0]} 2>&1 || true")
    assert f"{LOCAL}/current/" in installed, installed
    assert router.returncode(f"apk info -e {KMOD[0]}") != 0
    ok, said = stand_in.sync()
    assert not ok
    assert "there is no local repository" in said
    # The router routes as ever, the proxy included.
    online = stand_in.online
    client = online.client()
    assert client.probe("tcp", DIRECT_TARGET[0])["address"] == online.wan_address
    assert client.probe("tcp", PROXIED_TARGET[0])["address"] == PROXY[0]


@spec(CAPABILITY, "Sync through the proxy", "Router cannot reach GitHub directly")
def test_sync_goes_through_the_proxy(stand_in: Releases, data_disk: Disk, isp: Isp) -> None:
    del data_disk  # the local repository's place
    router = stand_in.router
    tag = stand_in.publish()
    with isp.blocking(RELEASES[1]):
        direct = f"uclient-fetch -q -T 10 -O /dev/null https://{RELEASES[0]}/repos/{REPOSITORY}"
        assert router.returncode(f"{direct}/releases") != 0
        ok, said = stand_in.sync()
    assert ok, said
    assert f"{tag} is current" in said
    assert stand_in.current() == tag


@spec(CAPABILITY, "Activate only when complete and verified", "Sync interrupted midway")
def test_an_interrupted_sync_changes_nothing(stand_in: Releases, data_disk: Disk) -> None:
    del data_disk  # the local repository's place
    router = stand_in.router
    previous = stand_in.synced()
    tag = stand_in.publish()
    releases.cut(stand_in.root, REPOSITORY, tag, CUT)
    try:
        ok, said = stand_in.sync()
    finally:
        releases.cut(stand_in.root, REPOSITORY, tag, None)
    assert not ok
    assert "the current release stays" in said
    assert stand_in.current() == previous
    assert tag not in stand_in.kept()
    # What apk and wrt-update read is the previous release's.
    for path in ("targets/packages/packages.adb", UPGRADE):
        assert f"/releases/{previous}/" in router.run(f"readlink -f {LOCAL}/current/{path}")
    assert KMOD[0] in router.run(f"apk search {KMOD[0]}")
    # The next sync that gets through makes it current.
    ok, said = stand_in.sync()
    assert ok, said
    assert stand_in.current() == tag


@spec(
    CAPABILITY, "Activate only when complete and verified", "File that does not match the manifest"
)
def test_a_file_that_does_not_match_is_refused(
    stand_in: Releases, data_disk: Disk, tmp_path: Path
) -> None:
    del data_disk  # the local repository's place
    previous = stand_in.synced()
    # The release is complete and its manifest is signed, but its upgrade image
    # is not the one the manifest lists.
    release = linked_copy(stand_in.assembled, tmp_path / "release")
    (image,) = release.glob("*-sysupgrade.tar.gz")
    changed = bytearray(image.read_bytes())
    changed[TAMPERED] ^= 1
    replace(image, bytes(changed))
    tag = stand_in.publish(release)
    ok, said = stand_in.sync()
    assert not ok
    assert f"{tag}: targets/{image.name} does not match the manifest" in said, said
    assert stand_in.current() == previous
    assert tag not in stand_in.kept()


@spec(CAPABILITY, "apk uses the local repository", "Install a kmod with WAN down")
def test_a_kmod_installs_with_the_wan_down(stand_in: Releases, data_disk: Disk) -> None:
    del data_disk  # the local repository's place
    router = stand_in.router
    stand_in.synced()
    assert router.returncode(f"apk info -e {KMOD[0]}") != 0, "the image carries it"
    router.run("ifdown wan")
    try:
        router.run(f"apk add {KMOD[0]}", timeout=120)
        router.run(f"modprobe {KMOD[1]}")
        assert KMOD[1] in router.run("cut -d' ' -f1 /proc/modules").split()
    finally:
        router.run(f"rmmod {KMOD[1]}; apk del {KMOD[0]}; ifup wan")
        stand_in.online.reconnected()


def _flip_a_bit(router: Router, path: str, at: int) -> None:
    """Change one byte of a file on the router: one bit of it."""
    router.run(
        'ucode -e \'let f = require("fs").open(ARGV[0], "r+"), at = +ARGV[1];'
        " f.seek(at); let b = ord(f.read(1)); f.seek(at); f.write(chr(b ^ 1)); f.close();'"
        f" -- {path} {at}"
    )


@spec(CAPABILITY, "Upgrade from local files", "Tampered image")
def test_a_tampered_image_is_refused(
    stand_in: Releases, data_disk: Disk, build_output: Path
) -> None:
    del data_disk  # the local repository's place
    router = stand_in.router
    stand_in.synced()
    image = router.run(f"ls {LOCAL}/current/{UPGRADE}")
    slots = {which: slot_sha256(router, which) for which in ("a", "b")}
    written = (slot(router), slots, boot_area_sha256(router))
    router.run(f"cp {image} {image}.whole")
    (unsigned,) = build_output.glob(UPGRADE)
    try:
        _flip_a_bit(router, image, TAMPERED)
        tampered = router.run("wrt-update 2>&1 || true", timeout=300)
        assert "Image check failed" in tampered, tampered
        # An image without a signature is refused as well: this build's own.
        router.put(unsigned, image)
        refused = router.run("wrt-update 2>&1 || true", timeout=300)
        assert "Image check failed" in refused, refused
    finally:
        router.run(f"mv {image}.whole {image}")
    slots = {which: slot_sha256(router, which) for which in ("a", "b")}
    assert (slot(router), slots, boot_area_sha256(router)) == written


@spec(CAPABILITY, "Candidates require opt-in", "Default channel")
def test_only_stable_releases_by_default(stand_in: Releases, data_disk: Disk) -> None:
    del data_disk  # the local repository's place
    router = stand_in.router
    stable = stand_in.publish()
    candidate = stand_in.publish(prerelease=True)
    ok, said = stand_in.sync()
    assert ok, said
    assert stand_in.current() == stable
    assert candidate not in stand_in.kept()
    # Candidates come once the administrator asks for them.
    router.run("uci set wrt-sync.main.channel=candidate && uci commit wrt-sync")
    try:
        ok, said = stand_in.sync()
    finally:
        router.run("uci set wrt-sync.main.channel=stable && uci commit wrt-sync")
    assert ok, said
    assert stand_in.current() == candidate


@spec(CAPABILITY, "Keep the most recent releases", "Sync a fourth release")
def test_the_three_latest_releases_stay(stand_in: Releases, data_disk: Disk) -> None:
    del data_disk  # the local repository's place
    while len(stand_in.kept()) < KEEP:
        stand_in.publish()
        ok, said = stand_in.sync()
        assert ok, said
    kept = stand_in.kept()
    assert len(kept) == KEEP
    tag = stand_in.publish()
    ok, said = stand_in.sync()
    assert ok, said
    assert stand_in.kept() == [tag, *kept[:-1]]


@spec(CAPABILITY, "Sync the device's own board", "Release with several boards")
def test_a_release_of_several_boards(
    stand_in: Releases, data_disk: Disk, board: Board, tmp_path: Path
) -> None:
    del data_disk  # the local repository's place
    # The release carries this board's set and, under another board's device
    # name, a set that is no build at all: the router must not even fetch it.
    other = next(other for other in load_all() if other.id != board.id)
    release = linked_copy(stand_in.assembled, tmp_path / "release")
    for asset in [path for path in release.iterdir() if board.device in path.name]:
        foreign = release / asset.name.replace(board.device, other.device)
        foreign.write_bytes(b"another board's asset\n")
    info = read_json(release / RELEASE_FILE, Release)
    assets = tuple(sorted(path.name for path in release.iterdir() if path.name != RELEASE_FILE))
    write_json(release / RELEASE_FILE, info.model_copy(update={"assets": assets}))
    tag = stand_in.publish(release)
    ok, said = stand_in.sync()
    assert ok, said
    assert stand_in.current() == tag
    fetched = releases.downloads(stand_in.root, REPOSITORY, tag)
    assert fetched
    assert all(board.device in name for name in fetched), fetched
    # The upgrade command takes the board's own image, which passes its checks.
    router = stand_in.router
    (image,) = router.run(f"ls {LOCAL}/current/{UPGRADE}").split()
    assert f"-{board.device}-" in image
    router.run("wrt-update -T", timeout=300)


@spec(CAPABILITY, "Sync the device's own board", "Another board's manifest")
def test_another_board_s_build_is_refused(
    stand_in: Releases, data_disk: Disk, board: Board, release_keys: Keys | None, tmp_path: Path
) -> None:
    del data_disk  # the local repository's place
    if release_keys is None:
        pytest.skip("naming another board in a signed manifest needs the session's release keys")
    previous = stand_in.synced()
    # Under the device's name, a validly signed manifest of another board's build.
    other = next(other for other in load_all() if other.id != board.id)
    release = linked_copy(stand_in.assembled, tmp_path / "release")
    manifest = release / f"{board.device}-manifest.json"
    content = read_json(manifest, Manifest)
    write_json(manifest, content.model_copy(update={"board": other.id, "device": other.device}))
    release_keys.sign_file(manifest)
    tag = stand_in.publish(release)
    ok, said = stand_in.sync()
    assert not ok
    assert f"of a build for {other.device}, not for {board.device}" in said, said
    assert stand_in.current() == previous
    assert tag not in stand_in.kept()
