"""Run the shell library's functions and awk programs (scripts/lib/, module-boundaries D1, D3)."""

import os
import subprocess
from typing import TYPE_CHECKING

from wrt_tests.model.repository import REPO_DIR

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

LIBRARY = REPO_DIR / "scripts" / "lib"
CORE = LIBRARY / "core.sh"
# core.sh finds the repository from the path of the script that loads it: here,
# one beside the scripts.
SCRIPT = REPO_DIR / "scripts" / "test"


def library(
    modules: str,
    command: str,
    *args: str,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``command`` in sh with core and ``modules`` loaded; ``args`` are its arguments."""
    script = f'. "{CORE}" && use {modules} && {command}'
    return subprocess.run(
        ["sh", "-c", script, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env,
    )


def awk_program(
    name: str,
    *args: str,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the library's awk program ``name`` on ``args``, in the C locale, as its module does."""
    return subprocess.run(
        ["awk", "-f", str(LIBRARY / name), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env={**os.environ, **(env or {}), "LC_ALL": "C"},
    )
