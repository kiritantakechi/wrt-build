# Spec Delta

## MODIFIED Requirements

### Requirement: Shares on the data disk
All shares SHALL point to directories under `@shares`. When the data disk is absent, the SMB service MUST NOT offer any shares: neither when the system boots without it, nor once it is unmounted while the service runs. The service SHALL offer the shares again when the disk is mounted again.

#### Scenario: Data disk absent
- **WHEN** the system boots without the data disk
- **THEN** the SMB service is not running, and no shares are accessible

#### Scenario: Data disk removed while sharing
- **WHEN** the data disk is unmounted, as a removal of its device unmounts it, while the SMB service offers its shares
- **THEN** within a few seconds the SMB service no longer runs and no LAN client can connect to it, nothing is written to the boot disk in the disk's place, and once the disk is mounted again the shares are offered again
