"""The router's trust in the session's own CA and release keys.

The sandbox's CA (``wrt_tests.sandbox.pki``) certifies the emulated internet's
servers, and the session's release keys (``wrt_tests.model.keys``) sign its
build. The router trusts both for the session only: the CA beside the system's
certificates, and the keys in place of the image's own trust anchors.
"""

from typing import TYPE_CHECKING

from wrt_tests.model.keys import APK_KEYS, FIRMWARE_KEYS

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.device.router import Router
    from wrt_tests.model.keys import Keys

# Where the router trusts the CA, and its Go programs (podman, tailscale) find it.
CA_ON_ROUTER = "/etc/ssl/certs/wrt-test-ca.crt"


def trust_ca(router: Router, workdir: Path) -> None:
    """Have ``router`` trust the CA of the sandbox in ``workdir``."""
    router.put(workdir / "pki" / "ca.crt", CA_ON_ROUTER)


def trust_keys(router: Router, keys: Keys) -> None:
    """Make ``keys`` the router's only trust anchors, in place of the image's own."""
    router.run(f"rm -f /{APK_KEYS}/* /{FIRMWARE_KEYS}/* && mkdir -p /{APK_KEYS} /{FIRMWARE_KEYS}")
    for anchors in (APK_KEYS, FIRMWARE_KEYS):
        for key in (keys.keyring / anchors).iterdir():
            router.put(key, f"/{anchors}/{key.name}")
