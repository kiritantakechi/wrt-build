# Spec Delta

## MODIFIED Requirements

### Requirement: Rebuild only what changed
Running the build entry points again SHALL rebuild only what changed since the last build, and all that the change affects. The patch and configuration steps SHALL leave every file whose content they do not change as it was, modification time included. A patch series that does not apply MUST leave the source tree as it was. The target's compiler flags SHALL count among the inputs of every target package and toolchain, so that no build keeps an object compiled with other flags. The toolchain SHALL be built anew when any of its files, or the generic kernel files its kernel headers come from, changes; every board SHALL then compile its packages anew with it, so that no build keeps an object compiled by another toolchain.

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

#### Scenario: Change a toolchain patch
- **WHEN** a patch of the toolchain is added, changed or removed, and a board is built again in the same tree
- **THEN** the toolchain is built anew with it, and the board compiles its packages anew, as the time reports show; a build of the other board compiles its packages anew too
