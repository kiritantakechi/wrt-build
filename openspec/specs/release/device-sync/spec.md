# release/device-sync Specification

## Purpose
Defines how the router syncs release artifacts through the proxy to a local repository on the data disk, and how apk and upgrades use these local artifacts. This way, updates do not depend on the quality of the router's direct connection to GitHub.

## Requirements

### Requirement: Sync through the proxy
The router SHALL run a sync container that downloads release artifacts to `/mnt/data/repo`. Its traffic passes through the container bridge and is routed by dae according to rules, so it does not depend on whether router-originated traffic can reach GitHub directly.

#### Scenario: Router cannot reach GitHub directly
- **WHEN** direct connections from the router to the Releases service are blocked and a sync is triggered
- **THEN** the sync still completes successfully

### Requirement: Activate only when complete and verified
A new release SHALL become the locally available version only after all of its files are downloaded and match the checksums in the build manifest. A partially downloaded release MUST NOT be visible to apk or the upgrade command.

#### Scenario: Sync interrupted midway
- **WHEN** a sync is interrupted halfway through
- **THEN** apk and the upgrade command still see the previous complete release

### Requirement: apk uses the local repository
apk SHALL install packages and kmods from the local repository, and the index signature MUST be verified with the release public key in the image.

#### Scenario: Install a kmod with WAN down
- **WHEN** with the WAN down, a kmod that is not preinstalled in the image but is present in the local repository is installed
- **THEN** the installation succeeds and the module loads

### Requirement: Upgrade from local files
The upgrade command SHALL write the upgrade image of the current release in the local repository to the inactive slot. An image with an invalid signature or no signature MUST be rejected.

#### Scenario: Tampered image
- **WHEN** one byte of the local upgrade image is modified and an upgrade is then run
- **THEN** the upgrade is rejected and neither slot is written

### Requirement: Candidates require opt-in
The device SHALL sync only stable releases by default. It SHALL sync prerelease candidates only after an administrator explicitly enables the candidate channel.

#### Scenario: Default channel
- **WHEN** a newer candidate and an older stable release both exist and the device syncs with the default settings
- **THEN** only the stable release is synced

### Requirement: Keep the most recent releases
The local repository SHALL keep the 3 most recent complete releases and delete older ones automatically.

#### Scenario: Sync a fourth release
- **WHEN** another sync completes while 3 releases are already present locally
- **THEN** the oldest release is deleted and 3 releases remain locally

### Requirement: Missing data disk does not affect operation
When the data disk is absent, sync and local apk installation SHALL be unavailable, but the installed system MUST keep running normally.

#### Scenario: No data disk attached
- **WHEN** a package installation is run with no data disk attached
- **THEN** the command reports that the local repository is unavailable, and routing and other core functions are unaffected
