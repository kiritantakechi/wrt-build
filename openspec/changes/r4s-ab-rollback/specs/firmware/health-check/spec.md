# Spec Delta

## Purpose

Defines what counts as "the new system booted successfully": on success, confirm the current slot; on failure during a trial boot, reboot so the bootloader's count advances and eventually triggers a rollback.

## ADDED Requirements

### Requirement: Built-in checks
After boot, the health check SHALL verify the following: userspace has finished starting; br-lan is up and has an address; dropbear is listening on the LAN address; uhttpd is listening on the LAN address; and every registered component check passes. WAN state MUST NOT be a criterion.

#### Scenario: WAN down, everything else healthy
- **WHEN** PPPoE cannot connect during a trial boot, and every other check is healthy
- **THEN** the health check reports success

#### Scenario: Web server not up
- **WHEN** uhttpd never listens on the LAN address within the check time limit
- **THEN** the health check reports failure

### Requirement: Components can register checks
Other components SHALL be able to register additional checks by installing a check program into a well-known directory. Each check returns "pass" or "fail". If any check fails, or does not return within the per-check time limit, the overall result MUST be failure.

#### Scenario: Registered check fails
- **WHEN** a check registered by a component returns failure
- **THEN** the health check reports failure, and the result names the failed check

#### Scenario: Check times out
- **WHEN** a check does not return within the per-check time limit
- **THEN** that check counts as failed, and the overall result is failure

### Requirement: Result handling by trial boot state
If the system is in the trial boot state (`upgrade_available` is 1):
- when the checks pass within the total time limit, the health check SHALL reset `bootcount` to zero and clear `upgrade_available` to 0, which confirms the current slot;
- when the checks fail or exceed the total time limit, the health check SHALL reboot the device.

If the system is already confirmed, a failed check SHALL only record the result and MUST NOT reboot.

#### Scenario: Check passes during trial boot
- **WHEN** the health check passes in the trial boot state
- **THEN** `upgrade_available` becomes 0, `bootcount` becomes 0, and all later reboots keep using this slot

#### Scenario: Check fails during trial boot
- **WHEN** the health check fails in the trial boot state
- **THEN** the device reboots

#### Scenario: Check fails on a confirmed system
- **WHEN** the system is already confirmed and the health check fails
- **THEN** the failure is recorded, and the device does not reboot

### Requirement: Slot status query
An administrator SHALL be able to run one command to see the current slot, whether it is confirmed, the result of the most recent health check, and the failed checks.

#### Scenario: Query status
- **WHEN** an administrator runs the slot status command
- **THEN** the output shows the current slot (a or b), whether it is confirmed, and the time and result of the most recent check, plus the failed checks on failure
