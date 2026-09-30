# Spec Delta

## ADDED Requirements

### Requirement: USB storage
The emulator SHALL provide a USB 3 host controller on which a test plugs a disk in, on a port it chooses, and pulls it out again while the system runs. The disk SHALL be attached through USB Attached SCSI, as the R4S's data disk is, so that the image's own UAS driver serves it.

#### Scenario: Hot-plug a USB disk
- **WHEN** a test plugs a disk in and then pulls it out
- **THEN** the kernel binds it to the `uas` driver at SuperSpeed and shows it as a block device, and after the removal the block device is gone
