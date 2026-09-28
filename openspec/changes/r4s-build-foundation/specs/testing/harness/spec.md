# Spec Delta

## Purpose

Turn spec scenarios into repeatable checks with one automated system test suite. The same tests run both on the emulator and on the device, which reduces device verification to one command plus a few hardware-specific checks.

## ADDED Requirements

### Requirement: One test per spec scenario
Every spec scenario that can be tested at the system level SHALL have exactly one corresponding test, whose marker names the capability, requirement, and scenario it covers. The test framework SHALL be able to generate a coverage report that lists the scenarios without a test.

#### Scenario: Generate coverage report
- **WHEN** a coverage report is generated for all current specs
- **THEN** the report lists the test for each scenario, and every scenario that has no test and is not marked "verified elsewhere" or "device-only" is listed separately

#### Scenario: Marker names a missing scenario
- **WHEN** a test is marked with a scenario that does not exist in the specs
- **THEN** the coverage check fails and names that test

### Requirement: One suite, two targets
The test suite SHALL run with the emulator and with the device as targets without modifying any test. The target is selected only through the target description file.

#### Scenario: Run on each target
- **WHEN** `just test` and `just test-device <host>` are each run
- **THEN** both runs collect the same set of tests; only tests marked as specific to one target are skipped on the other

### Requirement: Target-specific tests state a reason
Tests that can run only on the device, or only on the emulator, SHALL carry the corresponding target marker together with a reason. On the other target, these tests SHALL be skipped, with the reason listed in the report.

#### Scenario: Device-only tests on the emulator
- **WHEN** tests run on the emulator target
- **THEN** all device-only tests show as skipped, and the report gives the reason for each skipped test

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

### Requirement: One-command device verification
Device verification SHALL need only one command to run every test that can run on the device. Hardware-specific checks SHALL also exist as tests; steps that need manual action (for example unplugging and replugging power) SHALL be prompted by the test, which then waits for confirmation.

#### Scenario: Run on the device
- **WHEN** `just test-device <host>` is run against an R4S flashed with the image
- **THEN** all applicable tests run in turn, the terminal gives a clear prompt whenever manual action is needed, and the final report has the same format as an emulator run
