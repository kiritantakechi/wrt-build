# Spec Delta

## Purpose

Boot the shipped image itself in QEMU as an R4S, with a repeatable network topology and fault injection, so that every system-level scenario is verified without the device.

## ADDED Requirements

### Requirement: Boot the shipped artifacts
The emulator SHALL boot the shipped sysupgrade image itself:
- the kernel is extracted from the FIT in the image's boot partition;
- the disk is this image;
- the kernel boot arguments come from the image's `boot.scr`, replacing only the two hardware-related parts: the serial device and the root partition identifier.

The emulator MUST NOT use a separately built kernel or root filesystem.

#### Scenario: Verify artifact provenance
- **WHEN** an emulation run starts
- **THEN** the log records the sha256 of the image and kernel used, and they match the values in the build manifest; the boot arguments include `fstools_overlay_compression_type=zstd` from `boot.scr`

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
