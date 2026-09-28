# Spec Delta

## Purpose

Decides which slot each boot uses; falls back to the other slot automatically when a new system boots repeatedly without being confirmed; and turns kernel hangs and kernel panics into reboots that can be counted.

## ADDED Requirements

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
When `upgrade_available` is 1, every boot SHALL increment `bootcount`. When `bootcount` exceeds 3, the bootloader SHALL switch `boot_slot` to the other slot, clear `upgrade_available` and `bootcount`, and then boot that slot. When `upgrade_available` is 0, the bootloader MUST NOT increment `bootcount` and MUST NOT write to the SD card for counting.

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
The hardware watchdog SHALL start before the kernel begins running and stay active until userspace takes over. If userspace does not take over within the set time, the watchdog SHALL reset the device. After a kernel panic, the device SHALL reboot automatically within 10 seconds.

#### Scenario: Kernel panic
- **WHEN** a kernel panic occurs while the system is running
- **THEN** the device reboots within 10 seconds, and `bootcount` is incremented if it was in the trial boot state

#### Scenario: Early boot hang
- **WHEN** the kernel hangs before userspace starts
- **THEN** the device resets after the watchdog times out

#### Scenario: Userspace never takes over
- **WHEN** the kernel has booted, but userspace does not open the watchdog within the set time
- **THEN** the device resets
