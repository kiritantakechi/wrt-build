# Spec Delta

## MODIFIED Requirements

### Requirement: One toolchain for every board
All boards SHALL be built with the same toolchain: the cross toolchain for C and C++, and the Go and Rust toolchains that compile Go and Rust packages for the target. It SHALL be built once, from a configuration that carries no board's CPU flags, so that the C library and the Rust standard library it builds run on every board. A board's CPU tuning SHALL apply only to the packages built for that board. A board's build MUST NOT compile any part of the toolchain. A build MUST refuse a toolchain that was built with a board's CPU flags. A toolchain built with other flags than the configuration's SHALL be built anew. A failed build of the Go or Rust toolchain SHALL keep the cross toolchain built before it. A build MUST keep a cross toolchain built from the tree's own toolchain inputs, in every profile and however many makes run at once. Each board's build directories SHALL record the toolchain they were built with, and SHALL be built anew when, and only when, that is not the toolchain at hand.

#### Scenario: Toolchain free of board flags
- **WHEN** the flags the toolchain of a board's build was built with are inspected
- **THEN** they contain the `-mcpu` of no board, and they are the same for every board's build

#### Scenario: A toolchain built for a board
- **WHEN** a board's build starts on a toolchain that has no record of its flags, whose recorded flags hold a board's `-mcpu`, or whose C library or Rust standard library is not the one its record names
- **THEN** the build fails before building anything, and says to rebuild the toolchain

#### Scenario: Rebuild a changed toolchain
- **WHEN** the toolchain is built while its C library or Rust standard library is not the one its record names, as after a board's build rebuilt it, or while the configuration's flags differ from those recorded
- **THEN** it is built anew from the board-neutral configuration, never recorded as it is

#### Scenario: Keep the cross toolchain when Go or Rust fails
- **WHEN** the toolchain is built and the Go or Rust toolchain fails after the cross toolchain was built
- **THEN** the cross toolchain is recorded, and the next build of the toolchain keeps it and builds only what failed

#### Scenario: Keep the toolchain in buildbot mode
- **WHEN** a toolchain built for any profile is used by a board's build with the release profile, which builds in buildbot mode
- **THEN** the toolchain's record names the content of the tree's toolchain inputs, as in every mode, so it stays, and so do the boards' build directories that record it

#### Scenario: Check the version from parallel makes
- **WHEN** the makes of a parallel build check the toolchain's record of its inputs at the same time
- **THEN** none of them deletes a toolchain whose record names the content of the tree's toolchain inputs, and a toolchain whose record names other content is still deleted

#### Scenario: Keep each board's build with its toolchain
- **WHEN** a board's build starts after the toolchain was built, in any profile, for the board-neutral configuration or for another board
- **THEN** the board's build and staging directories stay if they record the toolchain at hand, and are built anew if they record another; the other board's directories stay as they are

#### Scenario: Boards share the toolchain
- **WHEN** two boards are built one after the other from the same tree
- **THEN** neither build compiles any part of the toolchain, and a build that does fails, naming what it compiled
