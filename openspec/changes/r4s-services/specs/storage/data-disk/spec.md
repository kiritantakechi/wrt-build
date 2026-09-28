# Spec Delta

## Purpose

Defines the USB SSD data disk's filesystem, subvolume layout, and mounting; how services that depend on the data disk wait for it to be ready before starting; where persistent logs live; and how the system degrades when the data disk is missing, so that write-heavy workloads stay off the SD card.

## ADDED Requirements

### Requirement: Btrfs data disk and subvolume layout
The data disk SHALL use btrfs and contain four subvolumes, `@containers`, `@downloads`, `@shares`, and `@logs`, plus a `.snapshots` subvolume for storing snapshots. Each subvolume SHALL be mounted at its own fixed mount point, with mount options that include zstd compression and noatime.

#### Scenario: Check mounts
- **WHEN** an initialized data disk is attached and the system boots
- **THEN** the four subvolumes are each mounted at their fixed mount points, and the mount options include `compress=zstd` and `noatime`

### Requirement: Data disk identified by UUID
The data disk SHALL be identified and mounted by filesystem UUID, independent of USB port position and device name. A disk whose UUID does not match MUST NOT be mounted at the data disk mount points.

#### Scenario: Move to another USB port
- **WHEN** the data disk is moved from one USB port to another and the system reboots
- **THEN** every subvolume is still mounted at its original mount point

#### Scenario: Insert another disk
- **WHEN** a disk with a different UUID is inserted
- **THEN** it is not mounted at the data disk mount points

### Requirement: Dependent services wait for the mount
Services that depend on the data disk (containers, file sharing, downloads) SHALL start only after their mount points are available, and SHALL restart when a mount point reappears. They MUST NOT write data to the SD card while a mount point is absent.

#### Scenario: Data disk mounts late
- **WHEN** the data disk mounts 30 seconds late during boot
- **THEN** the container and file-sharing services start running only after the mount completes, and no new data is written to the same-named directories on the SD card

### Requirement: Degraded mode without the data disk
When the data disk is absent, the services that depend on it SHALL NOT start, and routing, firewall, NAT, proxy, DNS, and VPN MUST keep working normally.

#### Scenario: Boot without the data disk
- **WHEN** the system boots without the data disk
- **THEN** LAN clients have normal internet access, the container and file-sharing services are not running, and the health check still passes

### Requirement: Persistent logs on the data disk
System logs SHALL be written continuously to `@logs` while the data disk is available, and SHALL rotate when they reach the size limit. The SD card MUST NOT hold persistent logs.

#### Scenario: View logs after reboot
- **WHEN** the system runs for a while and then reboots
- **THEN** the logs from before the reboot are still kept in `@logs`

### Requirement: Periodic read-only snapshots
`@containers` and `@shares` SHALL each get a daily read-only snapshot, stored in `.snapshots`, with the last 7 days retained. The administrator SHALL be able to take a snapshot manually at any time. The administrator SHALL be able to restore a single file from a snapshot.

#### Scenario: Expired snapshots are pruned
- **WHEN** the system has been running for more than 8 days
- **THEN** `.snapshots` retains only the 7 most recent daily snapshots for each of the two subvolumes

#### Scenario: Manual snapshot
- **WHEN** the administrator runs the manual snapshot command
- **THEN** a read-only snapshot with the current timestamp appears in `.snapshots`

#### Scenario: Restore a file from a snapshot
- **WHEN** a file in a share is deleted after a snapshot, and the administrator restores it from the snapshot as documented
- **THEN** the restored file matches its content before deletion
