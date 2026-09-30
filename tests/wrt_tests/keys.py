"""Release keys made for the test, and what the tests sign with them (r4s-release-pipeline D7).

A release is signed with an apk key (EC P-256, package indexes) and a firmware
key (usign, images and the manifest). ``Keys.make`` creates both and a keyring
that mirrors the image's trust anchors (etc/apk/keys, etc/opkg/keys), as
wrt-keyring holds the production ones; ``install_trust`` puts it on a router.
``sign`` runs scripts/release-sign.sh, the script CI signs releases with, on a
build with these keys.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from wrt_tests.router import Router

REPO_DIR = Path(__file__).resolve().parents[2]
RELEASE_SIGN = REPO_DIR / "scripts" / "release-sign.sh"
APK_KEYS = Path("etc/apk/keys")
FIRMWARE_KEYS = Path("etc/opkg/keys")


def _run(*command: str | Path) -> str:
    return subprocess.run(
        [str(arg) for arg in command], check=True, capture_output=True, text=True
    ).stdout.strip()


@dataclass(frozen=True, slots=True)
class Keys:
    """A pair of release keys and the keyring that trusts them."""

    apk: Path
    firmware: Path
    keyring: Path

    @classmethod
    def make(cls, directory: Path, name: str = "test") -> Self:
        """Create an apk key, a firmware key and their keyring in ``directory``."""
        (directory / "keyring" / APK_KEYS).mkdir(parents=True)
        (directory / "keyring" / FIRMWARE_KEYS).mkdir(parents=True)
        apk = directory / f"{name}.apk.key"
        firmware = directory / f"{name}.fw.key"
        _run("openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", apk)
        _run(
            *("openssl", "ec", "-in", apk, "-pubout"),
            *("-out", directory / "keyring" / APK_KEYS / f"wrt-{name}.pem"),
        )
        public = directory / f"{name}.fw.pub"
        _run("usign", "-G", "-s", firmware, "-p", public, "-c", f"wrt-build {name} key")
        fingerprint = _run("usign", "-F", "-p", public)
        shutil.copy(public, directory / "keyring" / FIRMWARE_KEYS / fingerprint)
        return cls(apk, firmware, directory / "keyring")

    @property
    def fingerprint(self) -> str:
        """The firmware key's usign fingerprint, the name devices know it by."""
        return _run("usign", "-F", "-s", self.firmware)

    def sign_file(self, path: Path) -> Path:
        """Sign ``path`` with the firmware key, as a release's manifest is; return the signature.

        The signature is a file of its own, never written through a link.
        """
        signature = path.with_name(f"{path.name}.sig")
        signature.unlink(missing_ok=True)
        _run("usign", "-S", "-m", path, "-s", self.firmware, "-x", signature)
        return signature

    def trust_also(self, other: Keys) -> None:
        """Add ``other``'s public keys to this keyring, as during a key rotation."""
        for anchors in (APK_KEYS, FIRMWARE_KEYS):
            for key in (other.keyring / anchors).iterdir():
                shutil.copy(key, self.keyring / anchors / key.name)


def install_trust(router: Router, keys: Keys) -> None:
    """Make ``keys`` the router's only trust anchors, in place of the image's own."""
    router.run(f"rm -f /{APK_KEYS}/* /{FIRMWARE_KEYS}/* && mkdir -p /{APK_KEYS} /{FIRMWARE_KEYS}")
    for anchors in (APK_KEYS, FIRMWARE_KEYS):
        for key in (keys.keyring / anchors).iterdir():
            router.put(key, f"/{anchors}/{key.name}")


def sign(build: Path, signed: Path, keys: Keys) -> Path:
    """Sign the outputs of ``build`` into ``signed`` with release-sign.sh; return ``signed``."""
    _run(
        *(RELEASE_SIGN, build, signed),
        *("--apk-key", keys.apk, "--fw-key", keys.firmware, "--keyring", keys.keyring),
    )
    return signed
