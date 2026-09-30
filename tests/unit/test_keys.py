"""Unit tests of wrt_tests.keys: release keys made for the test, and their keyring."""

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from wrt_tests.keys import APK_KEYS, FIRMWARE_KEYS, Keys

if TYPE_CHECKING:
    from pathlib import Path

# An index of the build under test: apk treats an empty one as broken.
INDEX = "targets/packages/packages.adb"


def _returncode(*command: str | Path) -> int:
    return subprocess.run(
        [str(arg) for arg in command], capture_output=True, check=False
    ).returncode


@pytest.fixture
def index(build_output: Path) -> Path:
    """Return a package index of the build under test."""
    return build_output / INDEX


def _signed(index: Path, path: Path, keys: Keys) -> Path:
    """Copy ``index`` to ``path``, signed with ``keys``' apk key alone."""
    shutil.copy(index, path)
    subprocess.run(
        ["apk", "--allow-untrusted", "--sign-key", keys.apk, "adbsign", "--reset-signatures", path],
        check=True,
        capture_output=True,
    )
    return path


def test_keys_sign_and_their_keyring_verifies(tmp_path: Path, index: Path) -> None:
    keys, other = Keys.make(tmp_path / "keys"), Keys.make(tmp_path / "other", "other")
    index = _signed(index, tmp_path / "packages.adb", keys)
    assert _returncode("apk", "--keys-dir", keys.keyring / APK_KEYS, "verify", index) == 0
    assert _returncode("apk", "--keys-dir", other.keyring / APK_KEYS, "verify", index) != 0

    message = tmp_path / "message"
    message.write_text("signed")
    subprocess.run(["usign", "-S", "-m", message, "-s", keys.firmware], check=True)
    assert _returncode("usign", "-V", "-q", "-m", message, "-P", keys.keyring / FIRMWARE_KEYS) == 0
    assert _returncode("usign", "-V", "-q", "-m", message, "-P", other.keyring / FIRMWARE_KEYS) != 0
    assert (keys.keyring / FIRMWARE_KEYS / keys.fingerprint).is_file()


def test_keyring_can_trust_two_keys(tmp_path: Path, index: Path) -> None:
    old, new = Keys.make(tmp_path / "old", "old"), Keys.make(tmp_path / "new", "new")
    new.trust_also(old)
    for keys in (old, new):
        signed = _signed(index, tmp_path / f"{keys.fingerprint}.adb", keys)
        assert _returncode("apk", "--keys-dir", new.keyring / APK_KEYS, "verify", signed) == 0
