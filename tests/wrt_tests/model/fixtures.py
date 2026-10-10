"""The fixtures of the build under test, as data (module-boundaries D6).

The emulator boots the build that emu-prepare recorded in its directory; its
manifest names the board and the profile. The session signs that build with
release keys of its own (the script CI signs releases with), and its router
trusts those keys instead of the image's, as a release image trusts the release
keys: upgrades and packages are the build's, signed. The upgrade drill
(r4s-release-pipeline D5) instead names the production-signed candidate in
$WRT_SIGNED; then nothing is signed here and the image's own trust anchors
decide.
"""

import os
from pathlib import Path

import pytest

from wrt_tests.model import boards
from wrt_tests.model.data import read_json
from wrt_tests.model.keys import Keys, sign
from wrt_tests.model.outputs import MANIFEST_FILE, SOURCE_FILE, EmulationSource, Manifest

UPGRADE_IMAGE = "targets/*-sysupgrade.tar.gz"
SIGNED_ENV = "WRT_SIGNED"


@pytest.fixture(scope="session")
def emulation_dir() -> Path:
    """Return the directory emu-prepare made from the image under test (scripts/test.sh)."""
    return Path(os.environ["LG_EMU_DIR"])


@pytest.fixture(scope="session")
def emulation_source(emulation_dir: Path) -> EmulationSource:
    """Return what emu-prepare recorded about the emulator's files."""
    return read_json(emulation_dir / SOURCE_FILE, EmulationSource)


@pytest.fixture(scope="session")
def build_output(emulation_source: EmulationSource) -> Path:
    """Return the output directory of the build the emulator boots."""
    return emulation_source.build


@pytest.fixture(scope="session")
def manifest(build_output: Path) -> Manifest:
    """Return the manifest of the build under test."""
    return read_json(build_output / MANIFEST_FILE, Manifest)


@pytest.fixture(scope="session")
def board(manifest: Manifest) -> boards.Board:
    """Return the board the build under test was built for, as its manifest names it."""
    return boards.load(manifest.board)


@pytest.fixture(scope="session")
def profile(manifest: Manifest) -> str:
    """Return the profile the build under test was built in, as its manifest names it."""
    return manifest.profile


@pytest.fixture(scope="session")
def release_keys(tmp_path_factory: pytest.TempPathFactory) -> Keys | None:
    """Return the session's release keys, or None when $WRT_SIGNED names a signed build."""
    if os.environ.get(SIGNED_ENV):
        return None
    return Keys.make(tmp_path_factory.mktemp("keys"))


@pytest.fixture(scope="session")
def signed_repo(
    build_output: Path, release_keys: Keys | None, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Return the build under test signed with the session's keys (or $WRT_SIGNED)."""
    if release_keys is None:
        return Path(os.environ[SIGNED_ENV])
    return sign(build_output, tmp_path_factory.mktemp("signed") / "build", release_keys)


@pytest.fixture(scope="session")
def signed_boards(
    board: boards.Board, signed_repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Return the signed builds as the sign job hands them on: this board's, named after it."""
    directory = tmp_path_factory.mktemp("boards")
    (directory / board.id).symlink_to(signed_repo)
    return directory


@pytest.fixture(scope="session")
def upgrade_image(signed_repo: Path) -> Path:
    """Return the signed single-slot upgrade image of the build under test."""
    (image,) = signed_repo.glob(UPGRADE_IMAGE)
    return image
