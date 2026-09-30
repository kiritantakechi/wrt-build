# testing/harness Specification

## Purpose
Turn spec scenarios into repeatable checks with one automated system test suite that runs against the emulator, so that no verification step needs a real board.

## Requirements

### Requirement: One test per spec scenario
Every spec scenario that can be tested at the system level SHALL have exactly one corresponding test, whose marker names the capability, requirement, and scenario it covers. The test framework SHALL be able to generate a coverage report that lists the scenarios without a test.

#### Scenario: Generate coverage report
- **WHEN** a coverage report is generated for all current specs
- **THEN** the report lists the test for each scenario, and every scenario that has no test and is not marked "verified elsewhere" is listed separately

#### Scenario: Marker names a missing scenario
- **WHEN** a test is marked with a scenario that does not exist in the specs
- **THEN** the coverage check fails and names that test

### Requirement: Python toolchain locked by uv
The test suite's Python environment SHALL be fully defined by `pyproject.toml` and `uv.lock`, including the Python interpreter version. Formatting and static checks use ruff and type checking uses ty, and both MUST pass.

#### Scenario: Lock file out of sync
- **WHEN** a dependency in `pyproject.toml` is changed but `uv.lock` is not updated
- **THEN** syncing the environment in locked mode fails

#### Scenario: Type error
- **WHEN** a test file contains a type error
- **THEN** the type check fails and points to the location of the error

### Requirement: Emulator run on every build
CI SHALL run the emulator tests for every firmware build. Any failing test MUST fail the whole pipeline, and results SHALL be published in JUnit format.

#### Scenario: Test failure
- **WHEN** the image from a build makes a test fail
- **THEN** the CI test stage fails, and the JUnit report shows that test and the failure reason
