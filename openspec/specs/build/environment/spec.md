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
The location of the build working directory SHALL be configurable: it holds the upstream source tree, the download cache, the compiler caches and the artifacts. It MUST be outside the project repository, so that the local machine can place it on an external case-sensitive volume. The compiler caches of every language SHALL live in the working directory beside the source tree, not inside it, so that they outlive the tree.

#### Scenario: Build directory on an external volume
- **WHEN** a full build runs with the build directory configured on an external volume
- **THEN** sources, download cache, the compiler caches of every language, and artifacts are all on that volume, and no build artifacts appear in the project repository's working tree

#### Scenario: A new source tree
- **WHEN** the source tree is removed and fetched anew, and the same sources are built again
- **THEN** the compiler caches are still there, and they serve the build's compilations

### Requirement: Rebuild only what changed
Running the build entry points again SHALL rebuild only what changed since the last build, and all that the change affects. The patch and configuration steps SHALL leave every file whose content they do not change as it was, modification time included. A patch series that does not apply MUST leave the source tree as it was. The target's compiler flags SHALL count among the inputs of every target package and toolchain, so that no build keeps an object compiled with other flags.

#### Scenario: Re-apply an unchanged series
- **WHEN** the patch step runs again with the same `upstream.lock` and the same patches
- **THEN** no file of the source tree changes, modification times included

#### Scenario: Change one patch
- **WHEN** one patch changes and the patch step runs again
- **THEN** exactly the files whose content changed get a new modification time

#### Scenario: A patch that does not apply
- **WHEN** the patch step runs with a series one of whose patches does not apply
- **THEN** it fails naming that patch, and every file of the source tree stays as it was

#### Scenario: Build again without changes
- **WHEN** a board is built twice in a row with no change to the sources, the patches or the configuration
- **THEN** the second build prepares, configures and compiles nothing, as its time report and its compiler caches' reports show

#### Scenario: Change the compiler flags
- **WHEN** the target's compiler flags change and a board is built again in the same tree
- **THEN** the toolchains and every target package are compiled again with the new flags, as the toolchains' record and the time report show

### Requirement: Build time report
Every build, of the host stage or of a board, SHALL record when each of its stages began and ended. At its end, it SHALL report the stages that took the most time. For each stage, the report SHALL give its share of the build's duration and the time during which it ran alone.

#### Scenario: Find what holds up a build
- **WHEN** a build finishes
- **THEN** its output lists the stages that took the most time, each with its wall share and its solo time, and the full record is kept with the build's logs
