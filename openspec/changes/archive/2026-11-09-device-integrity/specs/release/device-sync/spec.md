# Spec Delta

## MODIFIED Requirements

### Requirement: Activate only when complete and verified
A new release SHALL become the locally available version only after all of its files are downloaded and match the checksums in its signed build manifest, which MUST list the upgrade image and the package indexes. A partially downloaded release, or one whose files do not match its manifest, MUST NOT be visible to apk or the upgrade command. Nothing the sync downloads SHALL replace the verified manifest or add an upgrade image beside the one it names, and a release name the release service gives SHALL be refused unless it is a plain file name. A release SHALL be on the disk in full before it becomes the current one.

#### Scenario: Sync interrupted midway
- **WHEN** a sync is interrupted halfway through
- **THEN** apk and the upgrade command still see the previous complete release

#### Scenario: File that does not match the manifest
- **WHEN** a release's upgrade image differs from the checksum its signed manifest lists, and the device syncs it
- **THEN** the sync fails, and apk and the upgrade command still see the previous complete release

#### Scenario: Package archive that carries more than packages
- **WHEN** a release's package archive also carries a manifest, an upgrade image or a symbolic link, and the device syncs it
- **THEN** the sync fails, and apk and the upgrade command still see the previous complete release

#### Scenario: Release name that is no file name
- **WHEN** the release service names the newest release `..`, or a name holding a slash or a quote, and the device syncs
- **THEN** the sync fails before it writes anything, and apk and the upgrade command still see the previous complete release

#### Scenario: Power cut right after a sync
- **WHEN** the device loses power as soon as a sync has made a release current, and boots again
- **THEN** every file of the current release matches its manifest

### Requirement: Upgrade from local files
The upgrade command SHALL write the upgrade image of the current release in the local repository to the inactive slot: the image its signed manifest names, whatever else the release directory holds. An image with an invalid signature or no signature MUST be rejected.

#### Scenario: Tampered image
- **WHEN** one byte of the local upgrade image is modified and an upgrade is then run
- **THEN** the upgrade is rejected and neither slot is written

#### Scenario: Another image beside the release's
- **WHEN** the current release's directory holds a validly signed upgrade image of another release beside its own, under a name that sorts after it, and an upgrade is run
- **THEN** the upgrade writes the image the release's manifest names
