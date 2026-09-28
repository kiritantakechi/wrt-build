"""Unit tests of wrt_tests.specs: reading scenarios from OpenSpec deltas."""

from pathlib import Path

from wrt_tests.specs import ScenarioId, capability_of_module, parse_spec

DELTA = """# Spec Delta

## ADDED Requirements

### Requirement: Kept
Text.

#### Scenario: first
- **WHEN** a
- **THEN** b

#### Scenario: second
- **WHEN** a
- **THEN** b

## REMOVED Requirements

### Requirement: Gone
#### Scenario: never verified
- **WHEN** a
- **THEN** b

## MODIFIED Requirements

### Requirement: Changed
#### Scenario: third
- **WHEN** a
- **THEN** b
"""


def test_parse_spec_skips_removed_requirements(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.md"
    spec_file.write_text(DELTA)
    scenarios = parse_spec(spec_file, "demo/widget", change="demo-change")
    assert [scenario.id for scenario in scenarios] == [
        ScenarioId("demo/widget", "Kept", "first"),
        ScenarioId("demo/widget", "Kept", "second"),
        ScenarioId("demo/widget", "Changed", "third"),
    ]
    assert {scenario.change for scenario in scenarios} == {"demo-change"}


def test_capability_of_module() -> None:
    assert capability_of_module(Path("firmware/test_base_system.py")) == "firmware/base-system"
    assert capability_of_module(Path("testing/test_emulation.py")) == "testing/emulation"
    assert capability_of_module(Path("firmware/helpers.py")) is None
    assert capability_of_module(Path("firmware/deep/test_x.py")) is None
