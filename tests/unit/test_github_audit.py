"""Unit tests of scripts/github-audit.sh against a gh that answers from files.

The stand-in answers ``gh api <path> [--jq <filter>]`` with the JSON file named
after the path, as GitHub's API would for a repository set up that way.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

AUDIT = Path(__file__).resolve().parents[2] / "scripts" / "github-audit.sh"
REPOSITORY = "owner/repository"
GH = """#!/bin/sh
[ "$1" = api ] || exit 1
file="$(dirname -- "$0")/$(printf '%s' "$2" | tr / _).json"
[ -f "${file}" ] || exit 1
if [ "${3:-}" = --jq ]; then jq -r "$4" "${file}"; else cat "${file}"; fi
"""


def _settings(*, reviewers: int = 1, branches: tuple[str, ...] = ("main", "bump/*")) -> Any:  # noqa: ANN401 (JSON)
    """Return the API's answers for a repository set up as the release pipeline needs."""
    base = f"repos/{REPOSITORY}"
    return {
        f"{base}/environments/release-signing": {
            "protection_rules": [
                {"type": "required_reviewers", "reviewers": [{"type": "User"}] * reviewers}
            ]
        },
        f"{base}/environments/release-signing/deployment-branch-policies": {
            "branch_policies": [{"name": name} for name in branches]
        },
        f"{base}/rules/branches/main": [
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [{"context": "check"}, {"context": "upgrade-drill"}]
                },
            }
        ],
    }


def _audit(tmp_path: Path, answers: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    """Run github-audit.sh with the stand-in answering ``answers``."""
    directory = tmp_path / "bin"
    directory.mkdir()
    (directory / "gh").write_text(GH)
    (directory / "gh").chmod(0o755)
    for path, answer in answers.items():
        (directory / f"{path.replace('/', '_')}.json").write_text(json.dumps(answer))
    return subprocess.run(
        [AUDIT, REPOSITORY],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": f"{directory}{os.pathsep}{os.environ['PATH']}"},
    )


def test_a_repository_set_up_passes(tmp_path: Path) -> None:
    result = _audit(tmp_path, _settings())
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout


@pytest.mark.parametrize(
    ("answers", "finding"),
    [
        (_settings(reviewers=0), "release-signing runs without a reviewer's approval"),
        (
            _settings(branches=("main", "bump/*", "*")),
            "release-signing deploys from '* bump/* main'",
        ),
        ({}, "no environment release-signing"),
    ],
    ids=["no reviewer", "any branch", "no environment"],
)
def test_a_repository_without_approval_fails(
    tmp_path: Path, answers: dict[str, Any], finding: str
) -> None:
    result = _audit(tmp_path, answers)
    assert result.returncode != 0
    assert f"FAIL  {finding}" in result.stdout


def test_a_main_that_does_not_wait_for_the_drill_fails(tmp_path: Path) -> None:
    answers = _settings()
    (rules,) = answers[f"repos/{REPOSITORY}/rules/branches/main"]
    rules["parameters"]["required_status_checks"] = [{"context": "check"}]
    result = _audit(tmp_path, answers)
    assert result.returncode != 0
    assert "FAIL  main does not require upgrade-drill" in result.stdout
