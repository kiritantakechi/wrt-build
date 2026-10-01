# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: One toolchain for every board`
- TO: `### Requirement: The same toolchains for every board`

## MODIFIED Requirements

### Requirement: The same toolchains for every board
All boards SHALL be built with the same toolchains: the cross toolchain, and the Go and Rust toolchains that compile Go and Rust packages for the target. Each SHALL be built once, from a configuration that carries no board's CPU flags, so that the C library and the Rust standard library they build run on every board. A board's CPU tuning SHALL apply only to the packages built for that board. A board's build MUST NOT compile any part of a toolchain. A build MUST refuse toolchains built with a board's CPU flags. It MUST keep a cross toolchain built from the tree's own `toolchain/`, in every profile and however many makes run at once.

#### Scenario: Toolchain free of board flags
- **WHEN** the flags that the toolchains of a board's build were built with are inspected
- **THEN** they contain the `-mcpu` of no board, and they are the same for every board's build

#### Scenario: A toolchain built for a board
- **WHEN** a board's build starts on toolchains that have no record of their flags, whose recorded flags hold a board's `-mcpu`, or whose C library or Rust standard library is not the one their record names
- **THEN** the build fails before building anything, and says to rebuild the toolchains

#### Scenario: Rebuild a changed toolchain
- **WHEN** the toolchains are built while their C library or Rust standard library is not the one their record names, as after a board's build rebuilt one
- **THEN** they are built anew from the board-neutral configuration, never recorded as they are

#### Scenario: Keep the toolchain in buildbot mode
- **WHEN** a toolchain built for any profile is used by a board's build with the release profile, whose buildbot mode deletes a toolchain of another version of `toolchain/`
- **THEN** the toolchain carries the version stamp that names the last commit of `toolchain/`, so it stays, and so do the boards' build directories

#### Scenario: Check the version from parallel makes
- **WHEN** the makes of a parallel build in buildbot mode check the toolchain's version stamp at the same time
- **THEN** none of them deletes a toolchain whose stamp names the last commit of `toolchain/`, and a toolchain whose stamp names another commit is still deleted

#### Scenario: Boards share the toolchains
- **WHEN** two boards are built one after the other from the same tree
- **THEN** neither build compiles any part of a toolchain, and a build that does fails, naming the toolchain
