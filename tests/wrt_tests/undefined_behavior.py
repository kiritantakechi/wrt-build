"""UB-indicative warnings and their reviews (spec quality/undefined-behavior).

A build's report (``warnings.json``, written by ``scripts/build.sh``) holds every
warning of a UB-indicative option in the build of a package its image ships. The
register (``tests/reviewed-warnings.toml``) holds the warnings reviewed as not
undefined behavior, each with its reason. A review matches a warning on package,
option, file and function, never on the line, so that it survives upstream moving
code around. A review that names boards matches only their builds' warnings: what
GCC finds can depend on the optimization, and so on the board's ``-mcpu``.
"""

import tomllib
from datetime import date
from pathlib import Path
from typing import Annotated, override

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from wrt_tests import boards

REGISTER = Path(__file__).resolve().parents[1] / "reviewed-warnings.toml"
REPORT_FILE = "warnings.json"

type Key = tuple[str, str, str, str]


class _Located(BaseModel):
    """What locates a warning: its package, option, file and function (empty outside any)."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    package: Annotated[str, Field(min_length=1)]
    option: Annotated[str, Field(pattern=r"^-W[a-z0-9-]+$")]
    file: Annotated[str, Field(min_length=1)]
    function: str

    @property
    def key(self) -> Key:
        """Return what a review and a warning match on."""
        return (self.package, self.option, self.file, self.function)

    def _function(self) -> str:
        return f", function {self.function}" if self.function else ""


class Diagnostic(_Located):
    """A UB-indicative warning of a build's report."""

    line: Annotated[int, Field(gt=0)]

    @override
    def __str__(self) -> str:
        """Render as ``package: option at file:line, function f``."""
        return f"{self.package}: {self.option} at {self.file}:{self.line}{self._function()}"


class Review(_Located):
    """A warning reviewed as not undefined behavior: why, and when."""

    reason: Annotated[str, Field(min_length=1)]
    reviewed: date
    boards: Annotated[tuple[str, ...], Field(strict=False)] = ()

    def covers(self, board: str) -> bool:
        """Return whether the review applies to the builds of ``board``."""
        return not self.boards or board in self.boards

    @override
    def __str__(self) -> str:
        """Render as ``package: option in file, function f``."""
        return f"{self.package}: {self.option} in {self.file}{self._function()}"


def load_report(build_output: Path) -> list[Diagnostic]:
    """Return the UB-indicative warnings of the build in ``build_output``."""
    text = (build_output / REPORT_FILE).read_text()
    return TypeAdapter(list[Diagnostic]).validate_json(text)


def load_register(path: Path = REGISTER) -> list[Review]:
    """Return the reviews of ``path``, which name known boards and no warning twice."""
    entries = tomllib.loads(path.read_text()).get("warning", [])
    reviews = [Review.model_validate(entry) for entry in entries]
    known = {board.id for board in boards.load_all()}
    seen: set[Key] = set()
    for review in reviews:
        if unknown := set(review.boards) - known:
            msg = f"{review} names unknown boards: {', '.join(sorted(unknown))}"
            raise ValueError(msg)
        if review.key in seen:
            msg = f"{review} is reviewed twice"
            raise ValueError(msg)
        seen.add(review.key)
    return reviews


def unreviewed(report: list[Diagnostic], register: list[Review], board: str) -> list[Diagnostic]:
    """Return the warnings of ``board``'s build that no review covers."""
    reviewed = {review.key for review in register if review.covers(board)}
    return [warning for warning in report if warning.key not in reviewed]


def stale(register: list[Review], report: list[Diagnostic], board: str) -> list[Review]:
    """Return the reviews for ``board`` that match no warning of its build."""
    found = {warning.key for warning in report}
    return [review for review in register if review.covers(board) and review.key not in found]
