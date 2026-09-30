"""The private configuration and config-push, as the tests drive them (r4s-release-pipeline D6).

``ConfigRepository.create`` runs scripts/config-init.sh with an age key of the
test's own. Its secrets, dae configuration and uci templates are then written
the way an administrator does, sops encrypting each file for the recipient in
.sops.yaml, and ``push`` runs scripts/config-push.sh against the router.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

REPO_DIR = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_DIR / "scripts"
PUSH_TIMEOUT = 900
GIT_IDENTITY = ("-c", "user.name=wrt-build", "-c", "user.email=wrt-build@localhost")


@dataclass(frozen=True, slots=True)
class ConfigRepository:
    """A private configuration repository and the age key its secrets are encrypted to."""

    directory: Path
    age_key: Path

    @classmethod
    def create(cls, workdir: Path) -> Self:
        """Run config-init in ``workdir``/config, with a new age key."""
        repository = cls(workdir / "config", workdir / "age.txt")
        subprocess.run(
            [SCRIPTS / "config-init.sh", repository.directory],
            check=True,
            capture_output=True,
            env=repository.environment(),
        )
        return repository

    def environment(self) -> dict[str, str]:
        """Return the environment config-init and config-push run in."""
        return {
            **os.environ,
            "SOPS_AGE_KEY_FILE": str(self.age_key),
            "WRT_CONFIG_DIR": str(self.directory),
        }

    def _encrypt(self, name: str, plain: bytes) -> None:
        """Write the file ``name`` (relative to the repository) encrypted, as sops does."""
        encrypted = subprocess.run(
            ["sops", "encrypt", "--filename-override", name, "/dev/stdin"],
            input=plain,
            check=True,
            capture_output=True,
            cwd=self.directory,
            env=self.environment(),
        ).stdout
        (self.directory / name).write_bytes(encrypted)

    def write_secrets(self, secrets: dict[str, Any]) -> None:
        """Replace the secrets (YAML is JSON's superset: JSON goes in as it is)."""
        self._encrypt("secrets/secrets.enc.yaml", json.dumps(secrets).encode())

    def write_dae(self, name: str, text: str) -> None:
        """Replace a file of dae's configuration."""
        self._encrypt(f"dae/{name}.dae.enc", text.encode())

    def write_template(self, name: str, text: str) -> None:
        """Replace a uci template."""
        (self.directory / "uci" / f"{name}.uci.tmpl").write_text(text)

    def commit(self, message: str) -> None:
        """Commit everything, as the administrator does after an edit."""
        git = ("git", "-C", str(self.directory), *GIT_IDENTITY)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", message], check=True)

    def discard(self) -> None:
        """Drop every change since the last commit."""
        git = ("git", "-C", str(self.directory))
        subprocess.run([*git, "reset", "-q", "--hard"], check=True)
        subprocess.run([*git, "clean", "-q", "-d", "--force"], check=True)

    def push(self, host: str, identity: Path) -> subprocess.CompletedProcess[str]:
        """Run config-push against ``host``, logging in with ``identity``."""
        return subprocess.run(
            [SCRIPTS / "config-push.sh", host, "--identity", identity],
            capture_output=True,
            text=True,
            check=False,
            env=self.environment(),
            timeout=PUSH_TIMEOUT,
        )
