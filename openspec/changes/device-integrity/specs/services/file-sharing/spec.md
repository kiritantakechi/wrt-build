# Spec Delta

## MODIFIED Requirements

### Requirement: Shares on the data disk
All shares SHALL point to directories under `@shares`. When the data disk is absent, the SMB service MUST NOT offer any shares: neither when the system boots without it, nor once it is unmounted while the service runs, however long the system takes over the unmount. The service SHALL offer the shares again when the disk is mounted again. A share SHALL count as on a mounted disk only while every mount point that holds its directory is mounted.

#### Scenario: Data disk absent
- **WHEN** the system boots without the data disk
- **THEN** the SMB service is not running, and no shares are accessible

#### Scenario: Data disk removed while sharing
- **WHEN** the data disk is unmounted, as a removal of its device unmounts it, while the SMB service offers its shares
- **THEN** within a few seconds the SMB service no longer runs and no LAN client can connect to it, nothing is written to the boot disk in the disk's place, and once the disk is mounted again the shares are offered again

#### Scenario: Data disk removed while an unmount script runs
- **WHEN** the data disk is removed while the SMB service offers its shares, and a script that the system runs before it unmounts a disk takes several seconds
- **THEN** once the disk is unmounted the SMB service no longer runs, and nothing is written to the boot disk in the disk's place

#### Scenario: Share within a disk within another
- **WHEN** a share lies under a mount point that lies under another, and only the outer one is mounted, and the SMB service is reloaded
- **THEN** that share is not offered
