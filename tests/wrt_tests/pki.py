"""The sandbox's test CA and the certificate of the emulated internet's servers.

One CA per sandbox, made with openssl: the registry and headscale present its
certificate, and the router and the peers trust the CA for the length of the
test session only (it never enters the image). The certificates are valid from
long before now: the emulated router keeps its image's time, which lags the
runner's, as a router without NTP would.
"""

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

NOT_BEFORE = "20200101000000Z"
VALIDITY = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class Pki:
    """Where the CA and the servers' certificate are."""

    directory: Path

    @property
    def ca(self) -> Path:
        """The CA certificate, to trust."""
        return self.directory / "ca.crt"

    @property
    def trust(self) -> Path:
        """A directory with the CA certificate alone, for tools that read one.

        skopeo and podman's certs.d would take a key there for a client key.
        """
        return self.directory / "trust"

    @property
    def certificate(self) -> Path:
        """The servers' certificate."""
        return self.directory / "server.crt"

    @property
    def key(self) -> Path:
        """The servers' private key."""
        return self.directory / "server.key"


def _openssl(*args: str | Path) -> None:
    subprocess.run(["openssl", *map(str, args)], check=True, capture_output=True)


def issue(directory: Path, names: Sequence[str], addresses: Sequence[str]) -> Pki:
    """Create a CA in ``directory`` and a certificate for ``names`` and ``addresses``."""
    directory.mkdir(parents=True)
    pki = Pki(directory)
    key = ("-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes")
    not_after = f"{datetime.now(UTC) + VALIDITY:%Y%m%d%H%M%SZ}"
    validity = ("-not_before", NOT_BEFORE, "-not_after", not_after)
    _openssl(
        "req", "-x509", *key, "-keyout", directory / "ca.key", "-out", pki.ca,
        *validity, "-subj", "/CN=wrt-build test CA",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
    )  # fmt: skip
    alternatives = ",".join([*(f"DNS:{n}" for n in names), *(f"IP:{a}" for a in addresses)])
    extensions = directory / "server.ext"
    extensions.write_text(f"subjectAltName={alternatives}\nextendedKeyUsage=serverAuth\n")
    _openssl(
        "req", *key, "-keyout", pki.key, "-out", directory / "server.csr",
        "-subj", f"/CN={names[0]}",
    )  # fmt: skip
    _openssl(
        "x509", "-req", "-in", directory / "server.csr", "-CA", pki.ca,
        "-CAkey", directory / "ca.key", "-CAcreateserial", *validity,
        "-extfile", extensions, "-out", pki.certificate,
    )  # fmt: skip
    pki.trust.mkdir()
    (pki.trust / "ca.crt").write_bytes(pki.ca.read_bytes())
    return pki
