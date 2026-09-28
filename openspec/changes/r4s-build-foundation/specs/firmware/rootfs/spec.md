# Spec Delta

## Purpose

Define the format and behavior of the filesystems in the root partition: a read-only, compressed EROFS root filesystem, plus an f2fs overlay that compresses on write.

## ADDED Requirements

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

### Requirement: Image boots directly
Once written to a microSD card, the SD card image the build produces SHALL boot the NanoPi R4S 4GB straight to userspace, with no manual steps.

#### Scenario: Boot after flashing
- **WHEN** the image is written to a microSD card, the card is inserted into the R4S, and the R4S is powered on
- **THEN** the system finishes booting, and the management interface is reachable from the LAN port
