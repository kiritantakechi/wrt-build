# Spec Delta

## ADDED Requirements

### Requirement: Sync the device's own board
A device SHALL download, verify and activate only the asset set of its own board: the assets named after the OpenWrt device of its board name, whose signed manifest names that device. apk and the upgrade command SHALL use only that set.

#### Scenario: Release with several boards
- **WHEN** the current release carries the asset sets of several boards, and the device syncs it
- **THEN** only its own board's set is downloaded and verified, and the upgrade command writes its own board's upgrade image

#### Scenario: Another board's manifest
- **WHEN** the set named after the device carries a validly signed manifest of another board's build, and the device syncs it
- **THEN** the sync fails, and apk and the upgrade command still see the previous complete release

## MODIFIED Requirements

### Requirement: Activate only when complete and verified
A new release SHALL become the locally available version only after all of its files are downloaded and match the checksums in its signed build manifest, which MUST list the upgrade image and the package indexes. A partially downloaded release, or one whose files do not match its manifest, MUST NOT be visible to apk or the upgrade command.

#### Scenario: Sync interrupted midway
- **WHEN** a sync is interrupted halfway through
- **THEN** apk and the upgrade command still see the previous complete release

#### Scenario: File that does not match the manifest
- **WHEN** a release's upgrade image differs from the checksum its signed manifest lists, and the device syncs it
- **THEN** the sync fails, and apk and the upgrade command still see the previous complete release
