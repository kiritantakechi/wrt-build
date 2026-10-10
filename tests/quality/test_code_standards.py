"""quality/code-standards: one command enforces every rule and catches each violation."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from wrt_tests import spec

CAPABILITY = "quality/code-standards"
REPO = Path(__file__).resolve().parents[2]
SYMMETRIC_VERBS = (("mount", "unmount"), ("pack", "unpack"))


def _files() -> list[str]:
    listing = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [name for name in listing.split("\0") if name and (REPO / name).is_file()]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Return a scratch copy of the repository (a git work tree, nothing committed)."""
    copy = tmp_path / "repo"
    for name in _files():
        (copy / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / name, copy / name)
    subprocess.run(["git", "init", "-q", str(copy)], check=True)
    # The Python checks run in the tests' virtual environment, shared with the copy.
    environment = Path(sys.prefix)
    (copy / "tests" / environment.name).symlink_to(environment)
    return copy


def _run(repo: Path, script: str, *names: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repo / "scripts" / script), *names],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "UV_OFFLINE": "1"},
    )


def _break_indentation(path: Path) -> None:
    text = path.read_text()
    broken = re.sub(r"^\t(\S)", r"  \1", text, count=1, flags=re.MULTILINE)
    assert broken != text
    path.write_text(broken)


@spec(CAPABILITY, "Uniform formatting", "Unformatted code committed")
def test_unformatted_shell_fails(repo: Path) -> None:
    _break_indentation(repo / "scripts" / "fetch.sh")
    result = _run(repo, "check.sh", "shfmt")
    assert result.returncode != 0
    assert "FAIL  shfmt" in result.stdout
    assert re.search(r"^\+\t", result.stdout, re.MULTILINE), result.stdout


@spec(CAPABILITY, "All static checks pass", "New static check warning")
def test_shellcheck_warning_fails(repo: Path) -> None:
    with (repo / "scripts" / "fmt.sh").open("a") as script:
        script.write("echo $HOME\n")
    result = _run(repo, "check.sh", "shellcheck")
    assert result.returncode != 0
    assert re.search(r"In scripts/fmt\.sh line \d+:", result.stdout), result.stdout
    assert "SC2250" in result.stdout


@spec(CAPABILITY, "Common script skeleton", "New script added")
def test_new_script_without_skeleton_fails(repo: Path) -> None:
    script = repo / "scripts" / "thing-probe.sh"
    header = (
        "#!/bin/sh\n# thing-probe: probe the skeleton check.\n# Usage: scripts/thing-probe.sh\n"
    )
    script.write_text(header + "echo probe\n")
    script.chmod(0o755)
    result = _run(repo, "check.sh", "skeleton")
    assert result.returncode != 0
    assert "scripts/thing-probe.sh: the body must start with" in result.stderr
    assert "scripts/thing-probe.sh: no just recipe named thing-probe" in result.stderr


@spec(CAPABILITY, "Layered test harness", "Harness module imports from a higher layer")
def test_an_import_from_a_higher_layer_fails(repo: Path) -> None:
    # A module of the model layer that reaches up to the device layer.
    with (repo / "tests" / "wrt_tests" / "model" / "poll.py").open("a") as module:
        module.write("\nfrom wrt_tests.device.router import Router\n")
    result = _run(repo, "check.sh", "tach")
    assert result.returncode != 0
    assert "FAIL  tach" in result.stdout
    # tach reports on stderr: the module, and what it imports.
    assert "wrt_tests/model/poll.py" in result.stderr, result.stderr
    assert "wrt_tests.device.router" in result.stderr, result.stderr


@spec(CAPABILITY, "No dead code in the host-side code", "Harness module that nothing imports")
def test_a_harness_module_that_nothing_imports_fails(repo: Path) -> None:
    orphan = repo / "tests" / "wrt_tests" / "model" / "orphan.py"
    orphan.write_text('"""A module that nothing imports."""\n')
    result = _run(repo, "check.sh", "spec-coverage")
    assert result.returncode != 0
    assert "FAIL  spec-coverage" in result.stdout
    output = result.stdout + result.stderr
    assert "wrt_tests/model/orphan.py: no harness module or test imports it" in output, output


@spec(CAPABILITY, "Symmetric naming", "Unpaired operation")
def test_paired_operations_are_complete() -> None:
    recipes = set(
        subprocess.run(
            ["just", "--justfile", str(REPO / "justfile"), "--summary"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    )
    assert {"workdir-mount", "workdir-unmount"} <= recipes
    for verb, counterpart in SYMMETRIC_VERBS:
        for recipe in recipes:
            for one, other in ((verb, counterpart), (counterpart, verb)):
                if recipe.endswith(f"-{one}"):
                    assert f"{recipe.removesuffix(one)}{other}" in recipes, recipe


@spec(CAPABILITY, "One command to check and format", "Format then check")
def test_fmt_then_check_passes(repo: Path) -> None:
    _break_indentation(repo / "scripts" / "fetch.sh")
    flake = repo / "flake.nix"
    flake.write_text(flake.read_text().replace("  outputs =", "  outputs  =", 1))
    module = repo / "tests" / "wrt_tests" / "model" / "data.py"
    module.write_text(module.read_text().replace("import tomllib\n", "import   tomllib\n", 1))
    formatting = ("shfmt", "nixfmt", "ruff-format")
    assert _run(repo, "check.sh", *formatting).returncode != 0
    assert _run(repo, "fmt.sh", *formatting).returncode == 0
    result = _run(repo, "check.sh", *formatting)
    assert result.returncode == 0, result.stdout + result.stderr
