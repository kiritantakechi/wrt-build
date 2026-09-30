# Spec Delta

## MODIFIED Requirements

### Requirement: Trial boot counting and automatic rollback
When `upgrade_available` is 1, every boot SHALL increment `bootcount`. When `bootcount` exceeds 3, the bootloader SHALL switch `boot_slot` to the other slot, clear `upgrade_available` and `bootcount`, and then boot that slot. When `upgrade_available` is 0, the bootloader MUST NOT increment `bootcount` and MUST NOT write to the boot disk for counting.

#### Scenario: New slot fails repeatedly
- **WHEN** the new slot is in the trial boot state and three consecutive boots go unconfirmed
- **THEN** on the fourth boot the bootloader switches back to the original slot, and `upgrade_available` is cleared to 0

#### Scenario: No counting during normal operation
- **WHEN** the device reboots with `upgrade_available` at 0
- **THEN** `bootcount` stays the same, and the bootloader does not write the environment

#### Scenario: Current slot fails to load
- **WHEN** the current slot's kernel cannot be loaded
- **THEN** the bootloader tries the other slot within the same power cycle; if both slots fail, it stops in the bootloader instead of looping forever

### Requirement: Same slot logic on the device and in the emulator
Every board's bootloader and the emulator's bootloader SHALL be built from the same U-Boot source, and carry the same slot selection and rollback logic. They SHALL differ only in three board constants: the boot disk's MMC device number, the console arguments, and the command that starts the kernel in a slot's FIT. Every board's bootloader SHALL keep its environment on its boot disk, at the same offset. Its device tree SHALL number the boot disk's controller as the MMC device of its constants.

#### Scenario: Compare the two bootloaders
- **WHEN** the built-in environments of a board's shipped bootloader and of the emulator's bootloader are compared
- **THEN**:
  - they are identical apart from the three board constants;
  - the board's bootloader keeps its environment at the shared offset of the MMC device its constants name;
  - its device tree names the boot disk's controller as that MMC device
