# Spec Delta

## MODIFIED Requirements

### Requirement: Four-partition dual-slot layout
The board's boot disk SHALL use an MBR partition table containing four primary partitions in order: boot-A, root-A, boot-B, root-B. The boot disk is the SD card on the NanoPi R4S and the eMMC on the NanoPi R6S. U-Boot and its environment SHALL live in the reserved area before the first partition. Each root partition SHALL hold an EROFS root filesystem, immediately followed by that slot's own overlay.

#### Scenario: Inspect the partition table
- **WHEN** the boot disk's partition table is inspected after the factory image is flashed
- **THEN** it shows four primary partitions in the order boot-A, root-A, boot-B, root-B, with space for U-Boot and its environment before the first partition

### Requirement: Factory image
The factory image SHALL contain both slots A and B, each holding the same system version. The first boot after flashing the factory image SHALL go to slot A.

#### Scenario: First boot
- **WHEN** the factory image is written to the boot disk and the device is powered on
- **THEN** the system boots from slot A

#### Scenario: Slot B also boots
- **WHEN** the factory image is flashed and the device is manually switched to slot B
- **THEN** the system boots normally from slot B
