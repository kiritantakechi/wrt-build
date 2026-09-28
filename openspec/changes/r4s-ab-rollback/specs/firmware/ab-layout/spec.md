# Spec Delta

## Purpose

Defines the dual-system partition layout on the SD card and the formats of the two artifacts, the factory image and the single-slot upgrade image, as the foundation for upgrades without downtime and automatic rollback.

## ADDED Requirements

### Requirement: Four-partition dual-slot layout
The SD card SHALL use an MBR partition table containing four primary partitions in order: boot-A, root-A, boot-B, root-B. U-Boot and its environment SHALL live in the reserved area before the first partition. Each root partition SHALL hold an EROFS root filesystem, immediately followed by that slot's own overlay.

#### Scenario: Inspect the partition table
- **WHEN** the SD card's partition table is inspected after the factory image is flashed
- **THEN** it shows four primary partitions in the order boot-A, root-A, boot-B, root-B, with space for U-Boot and its environment before the first partition

### Requirement: Factory image
The factory image SHALL contain both slots A and B, each holding the same system version. The first boot after flashing the factory image SHALL go to slot A.

#### Scenario: First boot
- **WHEN** the factory image is written to the SD card and the device is powered on
- **THEN** the system boots from slot A

#### Scenario: Slot B also boots
- **WHEN** the factory image is flashed and the device is manually switched to slot B
- **THEN** the system boots normally from slot B

### Requirement: Single-slot upgrade image
The upgrade image SHALL contain only one slot's boot partition contents and root partition contents, plus metadata that identifies the target device. The upgrade image MUST NOT contain U-Boot, the U-Boot environment, or a partition table.

#### Scenario: Inspect upgrade image contents
- **WHEN** the contents of the upgrade image are listed
- **THEN** there are only the boot contents, the root contents, and the metadata, with no bootloader and no partition table

### Requirement: Fits a 4 GB SD card
The entire layout SHALL fit on a 4 GB microSD card.

#### Scenario: Write to a 4 GB card
- **WHEN** the factory image is written to a 4 GB microSD card
- **THEN** the write succeeds and both slots boot
