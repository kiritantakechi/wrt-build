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

### Requirement: Fixtures by layer
Each layer of the test harness SHALL provide the fixtures of its own domain. The suite's root configuration SHALL compose the layers' fixtures and define none of its own. A fixture that only one suite of tests uses SHALL live in that suite's directory.

#### Scenario: Fixture defined in the root configuration
- **WHEN** the suite's root configuration defines a fixture
- **THEN** the harness's structure check fails and names the fixture

### Requirement: One schema per data file
The tests SHALL read every data file of the repository and of the build's and the release's outputs through one schema for that file, which rejects unknown fields and values of the wrong type: the board descriptions, the registers of scenarios verified elsewhere and of reviewed warnings, the build's manifest and reports, the toolchain's record, and a release's metadata and manifests.

#### Scenario: Malformed data file
- **WHEN** an entry of a data file the tests read has an unknown field or a value of the wrong type
- **THEN** reading the file fails and names the file, the entry and the field

### Requirement: Waiting for a condition
The harness's polling helper SHALL call a probe until the probe answers with content, and return that answer. An empty answer SHALL count as no answer yet, whatever its type: `None`, `False`, zero, an empty string and an empty collection alike. When the time limit passes without an answer with content, the helper SHALL fail and name what it waited for.

#### Scenario: A probe answers empty first
- **WHEN** a probe answers with an empty string, then with an empty list, then with a value
- **THEN** the wait goes on through the empty answers, and returns the value

#### Scenario: No answer within the time limit
- **WHEN** a probe answers only with empty values until the time limit passes
- **THEN** the wait fails, and its error names what it waited for

### Requirement: Failures name the router's state
A test failure that involves the router SHALL show what the harness can still see of the router and its networks. A wait for a reboot that does not come SHALL show the command that was to reboot the router, the command's output and the console since it ran. A failing test with the router online SHALL show the LAN clients' addresses and routes, the router's WAN state with its log, and the emulated ISP's sessions with its log. Gathering this SHALL NOT change the test's outcome.

#### Scenario: A reboot that does not come
- **WHEN** a command detached on the router ends without rebooting it, and the harness waits for the reboot
- **THEN** the wait fails at its time limit, and the failure shows the command, its output and the console since it ran

#### Scenario: A failing test with the router online
- **WHEN** a test that uses the router online fails
- **THEN** its report has a section with the LAN clients' addresses and routes, the router's WAN state and log, and the ISP's sessions and log
