"""spec-coverage: map every spec scenario to its one test (design D13).

The report lists, for each scenario, the test that verifies it, or the job named in
``verified-elsewhere.toml``, or MISSING. Structural errors always fail:

* a ``@spec`` marker naming a scenario that does not exist;
* a scenario with more than one test, or with a test and an entry elsewhere;
* a spec test outside ``<domain>/test_<capability>.py``, a module test without
  exactly one ``@spec`` of that module's capability, or a ``@spec`` in ``unit/``.

Every scenario of the archived specs (``openspec/specs``, the system as built)
must be covered; with ``--change NAME`` so must those of that change in flight.
"""

import argparse
import contextlib
import io
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import override

import pytest
from pydantic import BaseModel, ConfigDict

from wrt_tests.model.data import read_toml
from wrt_tests.model.repository import REPO_DIR, TESTS_DIR
from wrt_tests.model.specs import Scenario, ScenarioId, capability_of_module, load_scenarios

OPENSPEC_DIR = REPO_DIR / "openspec"
ELSEWHERE_FILE = "verified-elsewhere.toml"
UNIT_DOMAIN = "unit"


@dataclass(frozen=True, slots=True)
class TestRef:
    """One test function (all its parametrized cases) and its markers."""

    module: Path
    function: str
    specs: tuple[ScenarioId, ...]

    @override
    def __str__(self) -> str:
        """Render as ``module::function``."""
        return f"{self.module.as_posix()}::{self.function}"


class VerifiedElsewhere(BaseModel):
    """A scenario that the build or CI verifies rather than a test, and what verifies it."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    capability: str
    requirement: str
    scenario: str
    by: str

    @property
    def id(self) -> ScenarioId:
        """Return the scenario's identity."""
        return ScenarioId(self.capability, self.requirement, self.scenario)


class _Collector:
    """pytest plugin object that keeps the collected items."""

    def __init__(self) -> None:
        self.items: list[pytest.Item] = []

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        self.items = list(session.items)


def collect_tests(tests_dir: Path = TESTS_DIR) -> list[TestRef]:
    """Collect the suite without running it and return one TestRef per test function."""
    collector = _Collector()
    with contextlib.redirect_stdout(io.StringIO()):  # pytest's own collection listing
        status = pytest.main(
            [
                *(
                    "--collect-only",
                    "-qq",
                    "-p",
                    "no:cacheprovider",
                    "-p",
                    "wrt_tests.model.markers",
                ),
                *("--rootdir", str(tests_dir), str(tests_dir)),
            ],
            plugins=[collector],
        )
    if status not in {pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED}:
        msg = f"collecting the tests failed ({status})"
        raise SystemExit(msg)
    refs: dict[tuple[Path, str], TestRef] = {}
    for item in collector.items:
        module = item.path.relative_to(tests_dir)
        function = getattr(item, "originalname", item.name)
        specs = tuple(ScenarioId(*mark.args) for mark in item.iter_markers("spec"))
        refs.setdefault((module, function), TestRef(module, function, specs))
    return list(refs.values())


def load_elsewhere(tests_dir: Path = TESTS_DIR) -> dict[ScenarioId, str]:
    """Scenarios verified by the build or CI itself, with who verifies them."""
    path = tests_dir / ELSEWHERE_FILE
    if not path.exists():
        return {}
    return {entry.id: entry.by for entry in read_toml(path, "scenario", VerifiedElsewhere)}


def structure_errors(tests: list[TestRef]) -> list[str]:
    """Violations of the directory rule and the one-marker rule."""
    errors: list[str] = []
    for test in tests:
        if test.module.parts[0] == UNIT_DOMAIN:
            if test.specs:
                errors.append(f"{test}: tests in unit/ must not carry @spec")
            continue
        capability = capability_of_module(test.module)
        if capability is None:
            errors.append(f"{test}: spec tests live in <domain>/test_<capability>.py")
        elif len(test.specs) != 1:
            errors.append(f"{test}: needs exactly one @spec, has {len(test.specs)}")
        elif test.specs[0].capability != capability:
            errors.append(f"{test}: @spec names {test.specs[0].capability}, module is {capability}")
    return errors


def coverage_errors(
    scenarios: list[Scenario], tests: list[TestRef], elsewhere: dict[ScenarioId, str]
) -> tuple[list[str], dict[ScenarioId, list[TestRef]]]:
    """Dangling markers and duplicates; also returns the tests of every scenario."""
    known = {scenario.id for scenario in scenarios}
    by_scenario: dict[ScenarioId, list[TestRef]] = defaultdict(list)
    errors: list[str] = []
    for test in tests:
        for scenario_id in test.specs:
            if scenario_id in known:
                by_scenario[scenario_id].append(test)
            else:
                errors.append(f"{test}: @spec names no scenario: {scenario_id}")
    for scenario_id, found in sorted(by_scenario.items()):
        if len(found) > 1:
            errors.append(f"{scenario_id}: {len(found)} tests: {', '.join(map(str, found))}")
    for scenario_id, by in sorted(elsewhere.items()):
        if scenario_id not in known:
            errors.append(f"verified-elsewhere.toml names no scenario: {scenario_id}")
        elif scenario_id in by_scenario:
            errors.append(f"{scenario_id}: has a test and is verified elsewhere ({by})")
    return errors, by_scenario


def main(argv: list[str] | None = None) -> int:
    """Print the coverage report; exit 1 on structural errors or uncovered required scenarios."""
    parser = argparse.ArgumentParser(prog="spec-coverage", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--change",
        action="append",
        default=[],
        metavar="NAME",
        help="require every scenario of this change to be covered (repeatable)",
    )
    parser.add_argument(
        "--summary", action="store_true", help="print the totals instead of every scenario"
    )
    parser.add_argument("--openspec", type=Path, default=OPENSPEC_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--tests", type=Path, default=TESTS_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    scenarios = load_scenarios(args.openspec)
    unknown = sorted(set(args.change) - {s.change for s in scenarios if s.change})
    if unknown:
        parser.error(f"no such change with specs: {', '.join(unknown)}")
    tests = collect_tests(args.tests.resolve())
    elsewhere = load_elsewhere(args.tests)
    errors = structure_errors(tests)
    duplicate_errors, by_scenario = coverage_errors(scenarios, tests, elsewhere)
    errors += duplicate_errors

    missing: list[Scenario] = []
    totals: Counter[str] = Counter()
    for scenario in sorted(scenarios, key=lambda s: (s.change or "", s.id)):
        if found := by_scenario.get(scenario.id):
            status, detail = "covered", str(found[0])
        elif by := elsewhere.get(scenario.id):
            status, detail = "elsewhere", by
        else:
            status, detail = "MISSING", ""
            if scenario.change is None or scenario.change in args.change:
                missing.append(scenario)
        totals[status] += 1
        if not args.summary:
            print(f"{status:<10} {scenario.id}  {detail}".rstrip())
    if args.summary:
        print(
            ", ".join(
                f"{totals[status]} {status}" for status in ("covered", "elsewhere", "MISSING")
            )
        )

    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    for scenario in missing:
        change = f"{scenario.change}: " if scenario.change else ""
        print(f"error: {change}no test for {scenario.id}", file=sys.stderr)
    return 1 if errors or missing else 0


if __name__ == "__main__":
    sys.exit(main())
