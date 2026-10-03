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
A new release SHALL become the locally available version only after all of its files are downloaded and match the checksums in its signed build manifest, which MUST list the upgrade image and the package indexes. A partially downloaded release, or one whose files do not match its manifest, MUST NOT be visible to apk or the upgrade command.

#### Scenario: Sync interrupted midway
- **WHEN** a sync is interrupted halfway through
- **THEN** apk and the upgrade command still see the previous complete release

#### Scenario: File that does not match the manifest
- **WHEN** a release's upgrade image differs from the checksum its signed manifest lists, and the device syncs it
- **THEN** the sync fails, and apk and the upgrade command still see the previous complete release

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

### Requirement: Sync the device's own board
A device SHALL download, verify and activate only the asset set of its own board: the assets named after the OpenWrt device of its board name, whose signed manifest names that device. apk and the upgrade command SHALL use only that set.

#### Scenario: Release with several boards
- **WHEN** the current release carries the asset sets of several boards, and the device syncs it
- **THEN** only its own board's set is downloaded and verified, and the upgrade command writes its own board's upgrade image

#### Scenario: Another board's manifest
- **WHEN** the set named after the device carries a validly signed manifest of another board's build, and the device syncs it
- **THEN** the sync fails, and apk and the upgrade command still see the previous complete release
