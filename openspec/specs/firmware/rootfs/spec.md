# firmware/rootfs Specification

## Purpose
Define the boot chain in front of the root partition and the format and behavior of the filesystems in it: a read-only, compressed EROFS root filesystem, plus an f2fs overlay that compresses on write.

## Requirements

### Requirement: EROFS root filesystem
The firmware image's root filesystem SHALL be EROFS compressed with lz4hc. The build MUST NOT produce squashfs or ext4 root filesystem images.

#### Scenario: Check build artifacts
- **WHEN** the build artifacts directory is inspected
- **THEN** it contains only EROFS-based images, and no squashfs or ext4 root filesystem images

#### Scenario: Check mounts on the router
- **WHEN** the mount information is inspected after the router boots
- **THEN** the filesystem type of the read-only root (`/rom`) is erofs

### Requirement: Writable layer is zstd-compressed f2fs
The writable overlay SHALL live in the same root partition, directly after EROFS, use f2fs formatted with the compression feature, and be mounted with zstd compression.

#### Scenario: First boot creates the overlay
- **WHEN** a freshly flashed image boots for the first time
- **THEN** `/overlay` is created as f2fs, and its mount options include zstd compression

### Requirement: Factory reset clears only the writable layer
A factory reset SHALL clear only the overlay, and the contents of the EROFS root filesystem MUST remain unchanged.

#### Scenario: Factory reset
- **WHEN** a factory reset is performed and the router reboots
- **THEN** the configuration returns to the factory state, an empty overlay is recreated, and the EROFS contents are identical to those at flash time

### Requirement: Complete R4S boot chain
The factory image the build produces SHALL carry everything the NanoPi R4S 4GB needs to boot it with no manual steps: the RK3399 loader at sector 64, and at sector 16384 a U-Boot FIT for the R4S with TF-A whose built-in environment holds the slot logic. Each slot's boot partition SHALL hold a kernel FIT whose default configuration carries the R4S device tree with both network ports enabled. There is no boot script: the slot logic lives in the bootloader (firmware/boot-rollback). The emulator runs the kernel and root filesystem of this image through a U-Boot built for QEMU; this requirement covers the parts that only the RK3399 can run.

#### Scenario: Inspect the boot chain
- **WHEN** the factory image is inspected
- **THEN** sector 64 holds an RK3399 SD boot loader; sector 16384 holds a U-Boot FIT whose default configuration is compatible with `friendlyarm,nanopi-r4s`, loads TF-A and boots with `run wrt_boot`; and the kernel FIT on both boot-A and boot-B carries a device tree compatible with `friendlyarm,nanopi-r4s` and `rockchip,rk3399`, with the GMAC and the PCIe controller enabled
