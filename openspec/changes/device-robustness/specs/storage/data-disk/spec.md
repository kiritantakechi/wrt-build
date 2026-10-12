# Spec Delta

## MODIFIED Requirements

### Requirement: Dependent services wait for the mount
Services that depend on the data disk (containers, file sharing, downloads) SHALL start only after their mount points are available, and SHALL restart when a mount point reappears. They MUST NOT write data to the boot disk while a mount point is absent. While no data disk is mounted at its mount point, the mount point SHALL be read-only, so that nothing written to a path on the data disk can land on the boot disk, whether the disk is not yet mounted or was unmounted while something used it.

#### Scenario: Data disk mounts late
- **WHEN** the data disk mounts 30 seconds late during boot
- **THEN** the container and file-sharing services start running only after the mount completes, and no new data is written to the same-named directories on the boot disk

#### Scenario: Data disk removed while in use
- **WHEN** the data disk is unmounted, as a removal of its device unmounts it, while the system uses it
- **THEN** creating a file or a directory under its mount point fails, the boot disk holds nothing under the mount point, and once the disk is mounted again its subvolumes are at their paths
