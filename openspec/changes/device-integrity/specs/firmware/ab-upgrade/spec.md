# Spec Delta

## MODIFIED Requirements

### Requirement: Trial boot after writing
After a successful write, the upgrade SHALL point `boot_slot` at the new slot, set `upgrade_available` to 1 and `bootcount` to 0, and then reboot. The new slot SHALL become the long-term slot only after the health check confirms it. A write that fails anywhere, a slot's boot or root partition, its overlay or the preserved configuration, MUST leave the U-Boot environment as it was, so that the device boots the running slot again. When the configuration is preserved, it SHALL be in the new slot before the upgrade points `boot_slot` at it.

#### Scenario: Reboot after upgrade
- **WHEN** the upgrade finishes writing
- **THEN** the device reboots into the new slot in the trial boot state

#### Scenario: Write that fails
- **WHEN** an upgrade image's root member cannot be read to its end while the upgrade writes the inactive slot
- **THEN** the upgrade reports the failure, `boot_slot`, `upgrade_available` and `bootcount` keep their values, and the device boots the slot it ran before

#### Scenario: Configuration in place before the switch
- **WHEN** a config-preserving upgrade has pointed `boot_slot` at the new slot
- **THEN** the new slot's boot partition already holds the configuration backup
