"""Read spec scenarios from the OpenSpec tree.

A capability lives at ``specs/<domain>/<name>/spec.md``: once archived under
``openspec/specs``, and while in flight as a delta under
``openspec/changes/<change>/specs``. Requirements are ``### Requirement:`` headings
and scenarios are ``#### Scenario:`` headings below them. Deltas group
requirements under ``## ADDED|MODIFIED|REMOVED|RENAMED Requirements``; removed
requirements have no scenarios to verify, and a renamed requirement is the
archived one under its new name.
"""

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from pathlib import Path

_SECTION = re.compile(r"^## (?P<kind>ADDED|MODIFIED|REMOVED|RENAMED) Requirements\s*$")
_REQUIREMENT = re.compile(r"^### Requirement:\s*(?P<name>.+?)\s*$")
_SCENARIO = re.compile(r"^#### Scenario:\s*(?P<name>.+?)\s*$")
_RENAME = re.compile(r"^-\s*(?P<end>FROM|TO):\s*`?###\s*Requirement:\s*(?P<name>.+?)`?\s*$")


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


def parse_renames(spec_file: Path) -> dict[str, str]:
    """Return the requirements a delta renames, each old name with its new one."""
    renames: dict[str, str] = {}
    renamed = False
    old: str | None = None
    for line in spec_file.read_text(encoding="utf-8").splitlines():
        if section := _SECTION.match(line):
            renamed = section["kind"] == "RENAMED"
        elif renamed and (end := _RENAME.match(line)):
            if end["end"] == "FROM":
                old = str(end["name"])
            elif old is not None:
                renames[old] = str(end["name"])
                old = None
    return renames


def load_scenarios(openspec_dir: Path) -> list[Scenario]:
    """Return every scenario of the archived specs and of the changes in flight.

    An archived requirement that a change in flight renames keeps its scenarios,
    under the new name: the system still has to meet them, and its tests follow
    the change.
    """
    changes = openspec_dir / "changes"
    deltas = [
        (change_dir.name, _capability(spec_file, change_dir / "specs"), spec_file)
        for change_dir in sorted(p for p in changes.iterdir() if p.is_dir() and p.name != "archive")
        for spec_file in sorted((change_dir / "specs").glob("*/*/spec.md"))
    ]
    renamed = {
        (capability, old): new
        for _, capability, spec_file in deltas
        for old, new in parse_renames(spec_file).items()
    }
    scenarios: list[Scenario] = []
    archived = openspec_dir / "specs"
    for spec_file in sorted(archived.glob("*/*/spec.md")):
        for scenario in parse_spec(spec_file, _capability(spec_file, archived), change=None):
            if new := renamed.get((scenario.id.capability, scenario.id.requirement)):
                scenarios.append(replace(scenario, id=replace(scenario.id, requirement=new)))
            else:
                scenarios.append(scenario)
    for change, capability, spec_file in deltas:
        scenarios += parse_spec(spec_file, capability, change=change)
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
