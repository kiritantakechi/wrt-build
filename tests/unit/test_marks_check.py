"""Unit tests of scripts/marks-check.sh on the paths it reads."""

import subprocess
from pathlib import Path

MARKS_CHECK = Path(__file__).resolve().parents[2] / "scripts" / "marks-check.sh"


def test_a_path_that_cannot_be_read_fails_the_check(tmp_path: Path) -> None:
    missing = tmp_path / "feed"
    result = subprocess.run([MARKS_CHECK, missing], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert f"cannot read every template under {missing}" in result.stderr
