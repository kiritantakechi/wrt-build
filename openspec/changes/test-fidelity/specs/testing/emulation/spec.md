# Spec Delta

## ADDED Requirements

### Requirement: The console's end is known
The emulator SHALL read the serial console for as long as the machine runs, and SHALL notice when the console ends, because QEMU exited, or can no longer be read. A wait for console output SHALL then fail at once and say why, instead of waiting out its time limit.

#### Scenario: QEMU exits while a test waits for the console
- **WHEN** QEMU exits while a test waits for a line on the console
- **THEN** the wait fails at once, saying that the console ended

## MODIFIED Requirements

### Requirement: USB storage
The emulator SHALL provide a USB 3 host controller on which a test plugs a disk in, on a port it chooses, and pulls it out again while the system runs. The disk SHALL be attached through USB Attached SCSI, as the boards' data disks are, so that the image's own UAS driver serves it. A disk SHALL stay plugged in through a forced power cut, as a disk in its port does, until the test pulls it out.

#### Scenario: Hot-plug a USB disk
- **WHEN** a test plugs a disk in and then pulls it out
- **THEN** the kernel binds it to the `uas` driver at SuperSpeed and shows it as a block device, and after the removal the block device is gone

#### Scenario: Power cut with a disk plugged in
- **WHEN** a test forces a power cut while a disk is plugged in, and then restarts the VM
- **THEN** the system that comes back finds the disk plugged in
