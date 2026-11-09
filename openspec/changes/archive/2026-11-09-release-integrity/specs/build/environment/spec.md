# Spec Delta

## MODIFIED Requirements

### Requirement: Common build entry points
The project SHALL provide named entry commands, including at least: fetch sources, apply patches, generate configuration, and build. When any substep fails, each entry point MUST exit with a nonzero status, and the remaining steps do not run. Each entry point SHALL pass its arguments to what it runs as they were given, each as one argument.

#### Scenario: Substep fails
- **WHEN** a substep of an entry command returns nonzero
- **THEN** the entry command exits with a nonzero status, and none of the later substeps run

#### Scenario: Full build in one command
- **WHEN** the full-build entry point runs in a fresh build directory
- **THEN** it fetches sources, applies patches, generates configuration, and builds, in that order, and finally produces the firmware image and the package repository

#### Scenario: An argument with a blank or a quote
- **WHEN** an entry point is given an argument that holds a blank, a quote or a shell metacharacter
- **THEN** what it runs gets that argument whole, as given, and nothing of it is run as a command
