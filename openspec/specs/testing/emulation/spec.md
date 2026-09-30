# testing/emulation Specification

## Purpose
Boot the shipped image itself in QEMU as the board it was built for, with a repeatable network topology and fault injection, so that every system-level scenario is verified without the device.

## Requirements

### Requirement: Boot the shipped artifacts
The emulator SHALL boot the shipped factory image itself, through the bootloader chain:
- the firmware is `uboot-wrt-qemu`, built from the same U-Boot source and slot logic as the R4S bootloader (firmware/boot-rollback);
- the SD card is this image, attached through an SD host controller, so U-Boot and Linux both see an MMC device and the U-Boot environment sits at the same offset as on the R4S;
- U-Boot selects the slot, loads that slot's kernel FIT and passes the kernel command line, as on the R4S.

The emulator MUST NOT use a separately built kernel or root filesystem, and MUST NOT pass a kernel or kernel command line to QEMU itself.

#### Scenario: Verify artifact provenance
- **WHEN** an emulation run starts
- **THEN** the log records the sha256 of the image and of the emulator's U-Boot, and they match the values in the build manifest; the running kernel is the one in the current slot's kernel FIT, and its command line carries `wrt.slot=a` and `fstools_overlay_compression_type=zstd`

### Requirement: Boot with the R4S board identity
The emulated machine SHALL boot with `friendlyarm,nanopi-r4s` as its board identifier, so that board scripts, port role assignment, and the board check of upgrade images follow the same paths as on the device.

#### Scenario: Read board name
- **WHEN** the system's board information is read in the emulator
- **THEN** the board name is `friendlyarm,nanopi-r4s`

### Requirement: Instruction set matches the device
The emulated CPU SHALL support the instruction set the image is compiled for (Cortex-A72 with the crypto extension), so that userspace programs run unchanged.

#### Scenario: Run userspace programs
- **WHEN** programs from the image run in the emulator
- **THEN** they run normally, with no illegal instruction errors

### Requirement: Repeatable network topology
The emulator SHALL provide two network ports with the same roles as on the R4S (WAN, LAN), each connected to its own isolated network namespace, in which an "upstream network" and "LAN clients" can run. The whole topology SHALL be set up without root privileges.

#### Scenario: LAN client gets an address
- **WHEN** after the emulator finishes booting, a client in the LAN namespace requests DHCP
- **THEN** the client gets an address in 10.0.0.0/24 and can reach 10.0.0.1

#### Scenario: No root privileges needed
- **WHEN** the emulation tests are started as a regular user
- **THEN** both the topology and the VM come up without sudo

### Requirement: Fault injection
The emulator SHALL provide the following means of fault injection:
- forced power cut (terminate the VM immediately);
- a hardware watchdog device;
- keystrokes sent to the serial console during boot;
- restoring the disk to its initial state between tests.

#### Scenario: Tests are isolated
- **WHEN** a test changes the configuration, and then the next test starts
- **THEN** the next test sees the disk in the image's initial state

#### Scenario: Forced power cut
- **WHEN** a test forces a power cut on the running system and then restarts the VM
- **THEN** the VM reboots from the same disk, and content already written to disk before the power cut is still there

### Requirement: USB storage
The emulator SHALL provide a USB 3 host controller on which a test plugs a disk in, on a port it chooses, and pulls it out again while the system runs. The disk SHALL be attached through USB Attached SCSI, as the R4S's data disk is, so that the image's own UAS driver serves it.

#### Scenario: Hot-plug a USB disk
- **WHEN** a test plugs a disk in and then pulls it out
- **THEN** the kernel binds it to the `uas` driver at SuperSpeed and shows it as a block device, and after the removal the block device is gone
