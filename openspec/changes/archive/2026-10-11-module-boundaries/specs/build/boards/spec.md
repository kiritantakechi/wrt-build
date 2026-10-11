# Spec Delta

## MODIFIED Requirements

### Requirement: One description per board
Every fact that differs between boards SHALL be declared once, in that board's description under `boards/`:
- the OpenWrt device, the board name and the SoC;
- the CPU tuning;
- the U-Boot variant and the directory its environment is built into;
- the boot disk and its kind (SD card or eMMC);
- the network ports with their roles and kernel drivers;
- the emulator's CPU model, core count, memory, boot disk kind and network ports.

The build, the bootloader glue, the emulator, the tests, CI and the release tooling SHALL take these facts from the descriptions. Apart from the descriptions, the per-board U-Boot fragments and the files the tests keep as a build and a release wrote them (`tests/fixtures`), no script, configuration, package, patch or test of the project SHALL name a board; documentation and specs may.

#### Scenario: A malformed description
- **WHEN** a board description lacks a required field, or has a field of the wrong kind
- **THEN** the code-standard checks fail and name the board and the field

#### Scenario: No board named outside its description
- **WHEN** the project's scripts, configuration, packages, patches and tests are searched for the supported boards' OpenWrt devices, board names and SoCs
- **THEN** they appear only in the board descriptions, the per-board U-Boot fragments and the files the tests keep as a build and a release wrote them
