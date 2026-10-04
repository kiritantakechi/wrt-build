# build/boards Specification

## Purpose
Describe each supported board once, as data, and build, test and release every board from the same tree, so that adding a board means adding its description rather than changing code.

## Requirements

### Requirement: One description per board
Every fact that differs between boards SHALL be declared once, in that board's description under `boards/`:
- the OpenWrt device, the board name and the SoC;
- the CPU tuning;
- the U-Boot variant and the directory its environment is built into;
- the boot disk and its kind (SD card or eMMC);
- the network ports with their roles and kernel drivers;
- the emulator's CPU model, core count, memory, boot disk kind and network ports.

The build, the bootloader glue, the emulator, the tests, CI and the release tooling SHALL take these facts from the descriptions. Apart from the descriptions and the per-board U-Boot fragments, no script, configuration, package, patch or test of the project SHALL name a board; documentation and specs may.

#### Scenario: A malformed description
- **WHEN** a board description lacks a required field, or has a field of the wrong kind
- **THEN** the code-standard checks fail and name the board and the field

#### Scenario: No board named outside its description
- **WHEN** the project's scripts, configuration, packages, patches and tests are searched for the supported boards' OpenWrt devices, board names and SoCs
- **THEN** they appear only in the board descriptions and the per-board U-Boot fragments

### Requirement: Supported boards
The project SHALL support two boards:
- the FriendlyElec NanoPi R4S: RK3399, booting from its SD card;
- the FriendlyElec NanoPi R6S: RK3588S, booting from its eMMC.

Every supported board SHALL be built, tested in the emulator, drilled and published in every run of the build workflow. No board may be left out of a run.

#### Scenario: Every board goes through the pipeline
- **WHEN** the build workflow's definition is inspected
- **THEN** its firmware, system-test and upgrade-drill jobs run once per board of `boards/`, and the publish job requires the asset set of each of them

### Requirement: One build per board from one tree
Each board SHALL be configured, built and tested by name (`just config`, `just build` and `just test`, given the board and a profile). Each board SHALL build in its own build, staging and output directories within the same source tree, so that building one board neither rebuilds nor overwrites another board's build. Each board's outputs SHALL go to `out/<board>/<profile>`.

#### Scenario: Two boards in one tree
- **WHEN** one board is built and then another in the same tree
- **THEN** the second build uses its own build, staging and output directories, and the first board's outputs and build objects stay as they were

#### Scenario: Build an unknown board
- **WHEN** a build is started for a board that has no description
- **THEN** it fails before configuring anything, and names the boards that have one

### Requirement: One toolchain for every board
All boards SHALL be built with the same toolchain: the cross toolchain for C and C++, and the Go and Rust toolchains that compile Go and Rust packages for the target. It SHALL be built once, from a configuration that carries no board's CPU flags, so that the C library and the Rust standard library it builds run on every board. A board's CPU tuning SHALL apply only to the packages built for that board. A board's build MUST NOT compile any part of the toolchain. A build MUST refuse a toolchain that was built with a board's CPU flags. A toolchain built with other flags than the configuration's SHALL be built anew. A failed build of the Go or Rust toolchain SHALL keep the cross toolchain built before it. A build MUST keep a cross toolchain built from the tree's own `toolchain/`, in every profile and however many makes run at once.

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
- **WHEN** a toolchain built for any profile is used by a board's build with the release profile, whose buildbot mode deletes a toolchain of another version of `toolchain/`
- **THEN** the toolchain carries the version stamp that names the last commit of `toolchain/`, so it stays, and so do the boards' build directories

#### Scenario: Check the version from parallel makes
- **WHEN** the makes of a parallel build in buildbot mode check the toolchain's version stamp at the same time
- **THEN** none of them deletes a toolchain whose stamp names the last commit of `toolchain/`, and a toolchain whose stamp names another commit is still deleted

#### Scenario: Boards share the toolchain
- **WHEN** two boards are built one after the other from the same tree
- **THEN** neither build compiles any part of the toolchain, and a build that does fails, naming what it compiled
