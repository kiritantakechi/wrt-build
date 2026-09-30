# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Boot with the R4S board identity`
- TO: `### Requirement: Boot with the board identity`

## ADDED Requirements

### Requirement: The board's cores
The emulated machine SHALL have the cores of the board's SoC, each with the capacity the SoC's device tree gives it, so that the kernel reports the board's big cores as it does on the board.

#### Scenario: Read core capacities
- **WHEN** the capacities of the cores are read in the emulator
- **THEN** they are the SoC's, scaled so that the highest is 1024, and the highest belong to the board's big cores

## MODIFIED Requirements

### Requirement: Boot the shipped artifacts
The emulator SHALL boot the shipped factory image of a board itself, through the bootloader chain:
- the firmware is `uboot-wrt-qemu`, built from the same U-Boot source and slot logic as the boards' bootloaders (firmware/boot-rollback);
- the boot disk is this image, attached as the board's kind of disk (an SD card or an eMMC) through an SD host controller, so U-Boot and Linux both see an MMC device and the U-Boot environment sits at the same offset as on the board;
- U-Boot selects the slot, loads that slot's kernel FIT and passes the kernel command line, as on the board.

The emulator MUST NOT use a separately built kernel or root filesystem, and MUST NOT pass a kernel or kernel command line to QEMU itself.

#### Scenario: Verify artifact provenance
- **WHEN** an emulation run starts
- **THEN**:
  - the log records the sha256 of the image and of the emulator's U-Boot, and they match the values in the build manifest;
  - the running kernel is the one in the current slot's kernel FIT;
  - its command line carries `wrt.slot=a` and `fstools_overlay_compression_type=zstd`

### Requirement: Boot with the board identity
The emulated machine SHALL boot with the board name of the board whose image it runs (`friendlyarm,nanopi-r4s` or `friendlyarm,nanopi-r6s`). Board scripts, port role assignment and the board check of upgrade images then follow the same paths as on the device.

#### Scenario: Read board name
- **WHEN** the system's board information is read in the emulator
- **THEN** the board name is the one of the board the image was built for

### Requirement: Instruction set matches the device
The emulated CPU SHALL support the instruction set the board's image is compiled for, so that userspace programs run unchanged: Cortex-A72 with the crypto extension for the NanoPi R4S, and Cortex-A76 with the crypto extension for the NanoPi R6S.

#### Scenario: Run userspace programs
- **WHEN** programs from the image run in the emulator
- **THEN** they run normally, with no illegal instruction errors

### Requirement: Repeatable network topology
The emulator SHALL provide the board's network ports, in the board's order and with its roles:
- the NanoPi R4S: WAN, LAN;
- the NanoPi R6S: LAN, WAN, LAN.

Each port SHALL be connected to its own isolated network namespace, in which an "upstream network" and "LAN clients" can run; a second LAN port gets a LAN segment of its own. The whole topology SHALL be set up without root privileges.

#### Scenario: LAN client gets an address
- **WHEN** after the emulator finishes booting, a client in the LAN namespace requests DHCP
- **THEN** the client gets an address in 10.0.0.0/24 and can reach 10.0.0.1

#### Scenario: No root privileges needed
- **WHEN** the emulation tests are started as a regular user
- **THEN** both the topology and the VM come up without sudo

#### Scenario: Clients on both LAN ports share one LAN
- **WHEN** the board has two LAN ports, and a client on each port's segment requests DHCP
- **THEN** both clients get addresses in 10.0.0.0/24 and reach each other through the router

### Requirement: USB storage
The emulator SHALL provide a USB 3 host controller on which a test plugs a disk in, on a port it chooses, and pulls it out again while the system runs. The disk SHALL be attached through USB Attached SCSI, as the boards' data disks are, so that the image's own UAS driver serves it.

#### Scenario: Hot-plug a USB disk
- **WHEN** a test plugs a disk in and then pulls it out
- **THEN** the kernel binds it to the `uas` driver at SuperSpeed and shows it as a block device, and after the removal the block device is gone
