# Spec Delta

## Purpose

Defines that an upgrade writes only the slot that is not currently running and carries the config over to the new slot; nothing that goes wrong during an upgrade affects the running system.

## ADDED Requirements

### Requirement: Write only the inactive slot
An upgrade SHALL write only the inactive slot's boot and root partitions. An upgrade MUST NOT modify the active slot, the U-Boot area, or the partition table.

#### Scenario: Upgrade from slot A
- **WHEN** an upgrade runs while the system is running on slot A
- **THEN** only the contents of boot-B and root-B change, and the checksums of boot-A, root-A, and the boot area match those from before the upgrade

#### Scenario: Power loss mid-upgrade
- **WHEN** power is lost while the inactive slot is being written
- **THEN** after power is restored, the device still boots normally from the original slot

### Requirement: New slot starts with a fresh overlay
After the new system is written, the inactive slot's existing overlay SHALL be discarded, and on its first boot the new system SHALL create a fresh overlay that contains only the migrated config.

#### Scenario: Leftover file in the old overlay
- **WHEN** slot B's existing overlay contains a user file, and an upgrade then runs and boots into slot B
- **THEN** the file does not exist in the new system

### Requirement: Config migration
When config is preserved (the default), the current system's config backup SHALL be placed where the new slot can read it on first boot, and restored on that first boot. When the user chooses not to preserve config, the new slot SHALL boot with the factory default config.

#### Scenario: Config-preserving upgrade
- **WHEN** an upgrade runs the default way and boots into the new slot
- **THEN** the new system's config matches the config from before the upgrade

#### Scenario: Upgrade without preserving config
- **WHEN** an upgrade runs with config preservation turned off
- **THEN** the new slot boots with the factory default config

### Requirement: Trial boot after writing
After a successful write, the upgrade SHALL point `boot_slot` at the new slot, set `upgrade_available` to 1 and `bootcount` to 0, and then reboot. The new slot SHALL become the long-term slot only after the health check confirms it.

#### Scenario: Reboot after upgrade
- **WHEN** the upgrade finishes writing
- **THEN** the device reboots into the new slot in the trial boot state

### Requirement: Reject mismatched images
An upgrade MUST reject an image whose metadata does not match this device, and MUST reject any file that is not a single-slot upgrade image.

#### Scenario: Image for another device
- **WHEN** an upgrade is run with an image built for another device
- **THEN** the upgrade is rejected and neither slot is written

### Requirement: Manual slot switch
An administrator SHALL be able to switch to the other slot manually, for example to go back to the previous version. After the switch, that slot boots in the trial boot state.

#### Scenario: Manually roll back to the previous version
- **WHEN** an administrator runs the switch command on slot B
- **THEN** the device reboots into slot A in the trial boot state, and the slot is confirmed after it passes the health check
