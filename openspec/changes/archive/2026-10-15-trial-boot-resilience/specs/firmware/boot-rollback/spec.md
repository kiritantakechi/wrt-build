# Spec Delta

## MODIFIED Requirements

### Requirement: Slot selection from a persistent variable
The bootloader SHALL boot the slot named by the persistently stored `boot_slot` variable. When this variable is missing or has an invalid value, the bootloader SHALL boot slot A. The current slot SHALL be passed to Linux on the kernel command line. The stored environment SHALL be kept in two copies, each write replacing the older one, so that a write cut short leaves the previous state in effect.

#### Scenario: Select slot B
- **WHEN** the device boots with `boot_slot` set to `b`
- **THEN** the root filesystem comes from root-B, and the kernel command line identifies the current slot as b

#### Scenario: Persistent variable missing or corrupted
- **WHEN** the persistent environment has no `boot_slot`, or both copies of the environment are corrupted
- **THEN** the system boots from slot A

#### Scenario: Environment write cut short
- **WHEN** a slot is on trial, and the copy that a later write of the environment went to is corrupted, as a reset in the middle of that write leaves it
- **THEN** the bootloader boots by the other copy: the trial slot again, with `bootcount` counting on

### Requirement: Same slot logic on the device and in the emulator
Every board's bootloader and the emulator's bootloader SHALL be built from the same U-Boot source, and carry the same slot selection and rollback logic. They SHALL differ only in three board constants: the boot disk's MMC device number, the console arguments, and the command that starts the kernel in a slot's FIT. Every board's bootloader SHALL keep the two copies of its environment on its boot disk, at the same two offsets. Its device tree SHALL number the boot disk's controller as the MMC device of its constants.

#### Scenario: Compare the two bootloaders
- **WHEN** the built-in environments of a board's shipped bootloader and of the emulator's bootloader are compared
- **THEN**:
  - they are identical apart from the three board constants;
  - the board's bootloader keeps the copies of its environment at the shared offsets of the MMC device its constants name;
  - its device tree names the boot disk's controller as that MMC device

## ADDED Requirements

### Requirement: The system writes the environment where the bootloader reads it
The bootloader SHALL pass the size and the offset of each copy of its environment to Linux on the kernel command line. The system SHALL read and write the environment at those places only, in the layout their number implies. A system started by a bootloader that names no places MUST NOT write the environment, and an upgrade MUST refuse to start before it writes anything.

#### Scenario: The environment where the bootloader names it
- **WHEN** the system boots and its access to the environment is configured
- **THEN** it reads and writes the copies at the sizes and offsets on the kernel command line, and nowhere else

#### Scenario: A bootloader that names no environment
- **WHEN** the bootloader that started the system named no places for its environment, and an upgrade is started
- **THEN** the upgrade refuses before writing a slot, and says why
