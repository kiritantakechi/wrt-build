# Spec Delta

## MODIFIED Requirements

### Requirement: Dependent services wait for the mount
Services that depend on the data disk (containers, file sharing, downloads) SHALL start only after their mount points are available, and SHALL restart when a mount point reappears. They MUST NOT write data to the boot disk while a mount point is absent.

#### Scenario: Data disk mounts late
- **WHEN** the data disk mounts 30 seconds late during boot
- **THEN** the container and file-sharing services start running only after the mount completes, and no new data is written to the same-named directories on the boot disk

### Requirement: Persistent logs on the data disk
System logs SHALL be written continuously to `@logs` while the data disk is available, and SHALL rotate when they reach the size limit. The boot disk MUST NOT hold persistent logs.

#### Scenario: View logs after reboot
- **WHEN** the system runs for a while and then reboots
- **THEN** the logs from before the reboot are still kept in `@logs`
