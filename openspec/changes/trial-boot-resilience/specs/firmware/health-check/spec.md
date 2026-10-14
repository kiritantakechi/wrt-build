# Spec Delta

## MODIFIED Requirements

### Requirement: Result handling by trial boot state
If the system is in the trial boot state (`upgrade_available` is 1):
- when the checks pass within the total time limit, the health check SHALL reset `bootcount` to zero and clear `upgrade_available` to 0, which confirms the current slot;
- when the checks fail or exceed the total time limit, the health check SHALL reboot the device.

If the system is already confirmed, a failed check SHALL only record the result and MUST NOT reboot.

The time limits SHALL run on a clock that setting the time of day does not move, as NTP or an administrator does during a boot.

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
