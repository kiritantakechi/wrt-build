# Spec Delta

## MODIFIED Requirements

### Requirement: Result handling by trial boot state
If the system is in the trial boot state (`upgrade_available` is 1):
- when the checks pass within the total time limit, the health check SHALL reset `bootcount` to zero and clear `upgrade_available` to 0, which confirms the current slot;
- when the checks fail or exceed the total time limit, the health check SHALL reboot the device.

If the system is already confirmed, a failed check SHALL only record the result and MUST NOT reboot.

The time limits SHALL run on a clock that setting the time of day does not move, as NTP or an administrator does during a boot.

The health check SHALL tell a U-Boot environment it cannot read from one that is not in the trial boot state: an environment it cannot read SHALL be a failed check of its own, and the device MUST NOT reboot for it. When the checks pass but the confirmation cannot be written, the result SHALL be a failure that names the confirmation, the slot SHALL stay in the trial boot state, and the device MUST NOT reboot.

#### Scenario: Check passes during trial boot
- **WHEN** the health check passes in the trial boot state
- **THEN** `upgrade_available` becomes 0, `bootcount` becomes 0, and all later reboots keep using this slot

#### Scenario: Check fails during trial boot
- **WHEN** the health check fails in the trial boot state
- **THEN** the device reboots

#### Scenario: Check fails on a confirmed system
- **WHEN** the system is already confirmed and the health check fails
- **THEN** the failure is recorded, and the device does not reboot

#### Scenario: Clock set during a trial boot
- **WHEN** the time of day is set forward by a day while a trial boot's checks are still failing, and they pass within the total time limit
- **THEN** the slot is confirmed, and the device does not reboot

#### Scenario: Environment that cannot be read
- **WHEN** the U-Boot environment cannot be read while the health check runs in the trial boot state
- **THEN** the result is a failure that names the environment, nothing is written to the environment, and the device does not reboot

#### Scenario: Confirmation that cannot be written
- **WHEN** the checks pass in the trial boot state but writing the U-Boot environment fails
- **THEN** the result is a failure that names the confirmation, `upgrade_available` stays 1, no log line says the slot is confirmed, and the device does not reboot
