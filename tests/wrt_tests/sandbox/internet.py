"""The emulated internet's servers (r4s-services D10, r4s-release-pipeline D7).

inet also serves a container registry (distribution), a tailnet's control
server (headscale, with its embedded DERP relay) and a stand-in for GitHub's
Releases API (wrt_tests.sandbox.releases), all over TLS with a certificate of the
sandbox's test CA. ``configure`` writes their configuration,
the CA, and the sandbox's own hosts file, which names them for the processes of
the sandbox (the router resolves them over DNS like any other name).
"""

import json
from typing import TYPE_CHECKING

from wrt_tests.sandbox import pki

if TYPE_CHECKING:
    from pathlib import Path

REGISTRY = ("registry.example.net", "203.0.113.30")
HEADSCALE = ("headscale.example.net", "203.0.113.40")
RELEASES = ("releases.example.net", "203.0.113.50")
TAILNET = ("100.64.0.0/10", "fd7a:115c:a1e0::/48")
WG_PEER = ("203.0.113.60", "2001:db8:ffff::60")
TS_PEER = ("203.0.113.70", "2001:db8:ffff::70")
SERVERS = (REGISTRY, HEADSCALE, RELEASES)


def configure(workdir: Path) -> pki.Pki:
    """Write the CA, the hosts file and the servers' configuration into the sandbox."""
    certificates = pki.issue(
        workdir / "pki", [name for name, _ in SERVERS], [address for _, address in SERVERS]
    )
    inet = workdir / "inet"
    inet.mkdir(parents=True, exist_ok=True)
    (workdir / "etc" / "hosts").write_text(
        "127.0.0.1 localhost\n::1 localhost\n"
        + "".join(f"{address} {name}\n" for name, address in SERVERS)
    )
    # JSON is YAML too: both servers read YAML configuration files.
    registry = {
        "version": 0.1,
        "log": {"level": "warn"},
        "storage": {"filesystem": {"rootdirectory": str(inet / "registry")}},
        "http": {
            "addr": f"{REGISTRY[1]}:443",
            "tls": {"certificate": str(certificates.certificate), "key": str(certificates.key)},
        },
    }
    (inet / "registry.yml").write_text(json.dumps(registry, indent=1))
    # skopeo wants a signature policy; the sandbox's own test images are unsigned.
    (inet / "policy.json").write_text(json.dumps({"default": [{"type": "insecureAcceptAnything"}]}))
    headscale = {
        "server_url": f"https://{HEADSCALE[0]}",
        "listen_addr": f"{HEADSCALE[1]}:443",
        "metrics_listen_addr": "127.0.0.1:9090",
        "grpc_listen_addr": "127.0.0.1:50443",
        "noise": {"private_key_path": str(inet / "noise_private.key")},
        "prefixes": {"v4": TAILNET[0], "v6": TAILNET[1], "allocation": "sequential"},
        "derp": {
            "server": {
                "enabled": True,
                "region_id": 999,
                "region_code": "sandbox",
                "region_name": "wrt-build sandbox",
                "stun_listen_addr": f"{HEADSCALE[1]}:3478",
                "private_key_path": str(inet / "derp_server_private.key"),
                "automatically_add_embedded_derp_region": True,
                "ipv4": HEADSCALE[1],
            },
            "urls": [],
            "paths": [],
            "auto_update_enabled": False,
        },
        "disable_check_updates": True,
        "database": {"type": "sqlite", "sqlite": {"path": str(inet / "headscale.sqlite")}},
        "tls_cert_path": str(certificates.certificate),
        "tls_key_path": str(certificates.key),
        "log": {"level": "warn"},
        "dns": {"magic_dns": False, "override_local_dns": False},
        "unix_socket": str(inet / "headscale.sock"),
        "unix_socket_permission": "0770",
    }
    (inet / "headscale.yaml").write_text(json.dumps(headscale, indent=1))
    return certificates
