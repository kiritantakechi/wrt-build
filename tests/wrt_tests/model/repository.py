"""Where the repository is: its root, and the directory of the tests."""

from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[3]
TESTS_DIR = REPO_DIR / "tests"
