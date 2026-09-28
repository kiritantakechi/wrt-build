"""Read spec scenarios from the OpenSpec tree.

A capability lives at ``specs/<domain>/<name>/spec.md``: once archived under
``openspec/specs``, and while in flight as a delta under
``openspec/changes/<change>/specs``. Requirements are ``### Requirement:`` headings
and scenarios are ``#### Scenario:`` headings below them. Deltas group
requirements under ``## ADDED|MODIFIED|REMOVED|RENAMED Requirements``; removed
requirements have no scenarios to verify.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from pathlib import Path

_SECTION = re.compile(r"^## (?P<kind>ADDED|MODIFIED|REMOVED|RENAMED) Requirements\s*$")
_REQUIREMENT = re.compile(r"^### Requirement:\s*(?P<name>.+?)\s*$")
_SCENARIO = re.compile(r"^#### Scenario:\s*(?P<name>.+?)\s*$")


@dataclass(frozen=True, slots=True, order=True)
class ScenarioId:
    """The address of one scenario: capability, requirement and scenario name."""

    capability: str
    requirement: str
    scenario: str

    @override
    def __str__(self) -> str:
        """Render as ``capability / requirement / scenario``."""
        return f"{self.capability} / {self.requirement} / {self.scenario}"


@dataclass(frozen=True, slots=True)
class Scenario:
    """A scenario and where it is specified."""

    id: ScenarioId
    change: str | None
    source: Path


def _capability(spec_file: Path, specs_dir: Path) -> str:
    return spec_file.parent.relative_to(specs_dir).as_posix()


def parse_spec(spec_file: Path, capability: str, change: str | None) -> list[Scenario]:
    """Return the scenarios of one spec file, skipping removed requirements."""
    scenarios: list[Scenario] = []
    requirement: str | None = None
    removed = False
    for line in spec_file.read_text(encoding="utf-8").splitlines():
        if section := _SECTION.match(line):
            removed = section["kind"] == "REMOVED"
            requirement = None
        elif heading := _REQUIREMENT.match(line):
            requirement = None if removed else str(heading["name"])
        elif (heading := _SCENARIO.match(line)) and requirement is not None:
            scenario_id = ScenarioId(capability, requirement, str(heading["name"]))
            scenarios.append(Scenario(scenario_id, change, spec_file))
    return scenarios


def load_scenarios(openspec_dir: Path) -> list[Scenario]:
    """Return every scenario of the archived specs and of the changes in flight."""
    scenarios: list[Scenario] = []
    archived = openspec_dir / "specs"
    for spec_file in sorted(archived.glob("*/*/spec.md")):
        scenarios += parse_spec(spec_file, _capability(spec_file, archived), change=None)
    changes = openspec_dir / "changes"
    for change_dir in sorted(p for p in changes.iterdir() if p.is_dir() and p.name != "archive"):
        specs_dir = change_dir / "specs"
        for spec_file in sorted(specs_dir.glob("*/*/spec.md")):
            capability = _capability(spec_file, specs_dir)
            scenarios += parse_spec(spec_file, capability, change=change_dir.name)
    return scenarios


def capability_of_module(module: Path) -> str | None:
    """Map ``<domain>/test_<name>.py`` to ``<domain>/<name>`` (underscores to hyphens)."""
    match module.parts:
        case (domain, filename) if filename.startswith("test_") and filename.endswith(".py"):
            return (
                f"{domain}/{filename.removeprefix('test_').removesuffix('.py').replace('_', '-')}"
            )
        case _:
            return None
