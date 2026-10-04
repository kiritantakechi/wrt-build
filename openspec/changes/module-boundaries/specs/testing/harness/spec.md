# Spec Delta

## ADDED Requirements

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
