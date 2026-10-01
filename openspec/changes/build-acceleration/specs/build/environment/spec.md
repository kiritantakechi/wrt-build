# Spec Delta

## MODIFIED Requirements

### Requirement: Configurable build directory outside the repository
The location of the build working directory SHALL be configurable: it holds the upstream source tree, the download cache, the compiler caches and the artifacts. It MUST be outside the project repository, so that the local machine can place it on an external case-sensitive volume. The compiler caches of every language SHALL live in the working directory beside the source tree, not inside it, so that they outlive the tree.

#### Scenario: Build directory on an external volume
- **WHEN** a full build runs with the build directory configured on an external volume
- **THEN** sources, download cache, the compiler caches of every language, and artifacts are all on that volume, and no build artifacts appear in the project repository's working tree

#### Scenario: A new source tree
- **WHEN** the source tree is removed and fetched anew, and the same sources are built again
- **THEN** the compiler caches are still there, and they serve the build's compilations

## ADDED Requirements

### Requirement: Rebuild only what changed
Running the build entry points again SHALL rebuild only what changed since the last build. The patch step SHALL leave every file whose content it does not change as it was, modification time included. A patch series that does not apply MUST leave the source tree as it was.

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
- **THEN** the second build prepares, configures and compiles nothing, as its time report shows

### Requirement: Build time report
Every build, of the host stage or of a board, SHALL record when each of its stages began and ended. At its end, it SHALL report the stages that took the most time. For each stage, the report SHALL give its share of the build's duration and the time during which it ran alone.

#### Scenario: Find what holds up a build
- **WHEN** a build finishes
- **THEN** its output lists the stages that took the most time, each with its wall share and its solo time, and the full record is kept with the build's logs
