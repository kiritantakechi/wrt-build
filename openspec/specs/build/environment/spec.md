# build/environment Specification

## Purpose
Define the Linux host environment for firmware builds: the local machine and CI use the same pinned tool set, and run builds through common entry points.

## Requirements

### Requirement: Pinned common host environment
The build environment SHALL be defined by a single Nix flake in the repository, with the versions of all host tools pinned by `flake.lock`. Local builds and CI builds MUST use the same `flake.lock`.

#### Scenario: Local and CI tool versions match
- **WHEN** the build environment is entered on the local Linux VM and in CI, and each outputs its host tool version list
- **THEN** the two lists are identical

#### Scenario: Tool updates require a lock change
- **WHEN** someone wants to change the version of a host tool
- **THEN** the change can only be made by modifying `flake.lock`, and it leaves a record in version control

### Requirement: Build only on Linux hosts
Builds SHALL run only on Linux hosts. When a build entry point is invoked on a non-Linux host, it MUST fail before fetching any source, with a clear message.

#### Scenario: Run directly on macOS
- **WHEN** any build entry point that fetches or compiles source is run on macOS
- **THEN** the command exits immediately with a nonzero status, tells the user to run it in the Linux VM or CI instead, and creates no source or download directories

### Requirement: Common build entry points
The project SHALL provide named entry commands, including at least: fetch sources, apply patches, generate configuration, and build. When any substep fails, each entry point MUST exit with a nonzero status, and the remaining steps do not run.

#### Scenario: Substep fails
- **WHEN** a substep of an entry command returns nonzero
- **THEN** the entry command exits with a nonzero status, and none of the later substeps run

#### Scenario: Full build in one command
- **WHEN** the full-build entry point runs in a fresh build directory
- **THEN** it fetches sources, applies patches, generates configuration, and builds, in that order, and finally produces the firmware image and the package repository

### Requirement: Configurable build directory outside the repository
The location of the build working directory (upstream source tree, download cache, compiler cache, artifacts) SHALL be configurable, and it MUST be outside the project repository, so the local machine can place it on an external case-sensitive volume.

#### Scenario: Build directory on an external volume
- **WHEN** a full build runs with the build directory configured on an external volume
- **THEN** sources, download cache, compiler cache, and artifacts are all on that volume, and no build artifacts appear in the project repository's working tree
