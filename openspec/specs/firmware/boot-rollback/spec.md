# firmware/boot-rollback Specification

## Purpose
Decides which slot each boot uses; falls back to the other slot automatically when a new system boots repeatedly without being confirmed; and turns kernel hangs and kernel panics into reboots that can be counted.

## Requirements

### Requirement: Slot selection from a persistent variable
The bootloader SHALL boot the slot named by the persistently stored `boot_slot` variable. When this variable is missing or has an invalid value, the bootloader SHALL boot slot A. The current slot SHALL be passed to Linux on the kernel command line.

#### Scenario: Select slot B
- **WHEN** the device boots with `boot_slot` set to `b`
- **THEN** the root filesystem comes from root-B, and the kernel command line identifies the current slot as b

#### Scenario: Persistent variable missing or corrupted
- **WHEN** the persistent environment has no `boot_slot`, or the whole environment block is corrupted
- **THEN** the system boots from slot A

### Requirement: Persistent environment cannot override boot logic
Only the runtime variables `boot_slot`, `bootcount`, and `upgrade_available` SHALL be read from the persistent environment. The slot selection and rollback logic MUST come from the bootloader itself and cannot be replaced by same-named variables in the persistent environment.

#### Scenario: Custom boot command in persistent environment
- **WHEN** someone writes a custom boot command into the persistent environment and reboots
- **THEN** the bootloader still uses its own built-in slot selection logic

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

### Requirement: Hangs and panics become reboots
The hardware watchdog SHALL start before the kernel begins running and stay active until userspace takes over: the bootloader SHALL start it with a 60-second timeout, and the kernel SHALL keep a running watchdog fed for at most 90 seconds until userspace opens it. Once userspace feeds the watchdog, a hang that stops the feeding SHALL reset the device. After a kernel panic, the device SHALL reboot automatically within 10 seconds. Every such reboot during a trial boot SHALL count toward rollback.

#### Scenario: Kernel panic
- **WHEN** a kernel panic occurs while the system is running
- **THEN** the device reboots within 10 seconds, and `bootcount` is incremented if it was in the trial boot state

#### Scenario: Userspace stops feeding the watchdog
- **WHEN** the process that feeds the watchdog stops feeding it during a trial boot
- **THEN** the device resets after the watchdog times out, and `bootcount` is incremented

#### Scenario: Watchdog armed before the kernel
- **WHEN** the configuration of the shipped bootloader and kernel is inspected
- **THEN** the bootloader starts the DesignWare watchdog with a 60-second timeout, the kernel has the DesignWare driver built in and keeps a watchdog that is already running fed, and the kernel command line limits that to 90 seconds (`watchdog.open_timeout=90`)

### Requirement: Same slot logic on the device and in the emulator
Every board's bootloader and the emulator's bootloader SHALL be built from the same U-Boot source, and carry the same slot selection and rollback logic. They SHALL differ only in three board constants: the boot disk's MMC device number, the console arguments, and the command that starts the kernel in a slot's FIT. Every board's bootloader SHALL keep its environment on its boot disk, at the same offset. Its device tree SHALL number the boot disk's controller as the MMC device of its constants.

#### Scenario: Compare the two bootloaders
- **WHEN** the built-in environments of a board's shipped bootloader and of the emulator's bootloader are compared
- **THEN**:
  - they are identical apart from the three board constants;
  - the board's bootloader keeps its environment at the shared offset of the MMC device its constants name;
  - its device tree names the boot disk's controller as that MMC device
