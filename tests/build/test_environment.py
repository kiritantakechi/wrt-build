"""build/environment: the build entry points refuse macOS and stop at a failed step."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from wrt_tests import spec

CAPABILITY = "build/environment"
REPO = Path(__file__).resolve().parents[2]
SOURCE_ENTRY_POINTS = ("fetch", "patch", "config", "build", "toolchain-build")


@pytest.fixture
def macos(tmp_path: Path) -> dict[str, str]:
    """Return an environment whose uname reports Darwin, like a macOS host."""
    uname = shutil.which("uname")
    assert uname is not None
    shim = tmp_path / "bin" / "uname"
    shim.parent.mkdir()
    shim.write_text(f'#!/bin/sh\n[ "$1" = -s ] && echo Darwin || exec {uname} "$@"\n')
    shim.chmod(0o755)
    return {**os.environ, "PATH": f"{shim.parent}:{os.environ['PATH']}"}


@spec(CAPABILITY, "只在 Linux 宿主机上构建", "在 macOS 上直接运行")
@pytest.mark.parametrize("entry_point", SOURCE_ENTRY_POINTS)
def test_macos_is_refused(entry_point: str, macos: dict[str, str], tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    result = subprocess.run(
        [str(REPO / "scripts" / f"{entry_point}.sh")],
        env={**macos, "WRT_WORKDIR": str(workdir)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "only on Linux" in result.stderr
    assert list(workdir.iterdir()) == []


@spec(CAPABILITY, "统一的构建入口", "子步骤失败")
def test_failed_step_stops_the_build(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "work"
    not_a_directory.write_text("")
    result = subprocess.run(
        ["just", "--justfile", str(REPO / "justfile"), "build", "dev"],
        env={**os.environ, "WRT_WORKDIR": str(not_a_directory)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "scripts/fetch.sh" in result.stderr
    assert "scripts/patch.sh" not in result.stderr
    assert "scripts/build.sh" not in result.stderr
