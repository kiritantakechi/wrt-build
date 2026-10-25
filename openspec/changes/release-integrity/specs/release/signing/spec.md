# Spec Delta

## MODIFIED Requirements

### Requirement: Signing targets
For every board's build, the signing job SHALL sign all package indexes with the release apk key, and the factory image and the upgrade image with the release firmware key. Before signing, it MUST verify that every file its board's build manifest lists, these artifacts among them, matches the checksum recorded there. It SHALL take each build as the build of the board its artifact is named after, refuse a manifest that names another board, a malformed checksum line or a file that is no plain path inside the build, and pass on only the files the manifest lists.

#### Scenario: Artifact does not match the manifest
- **WHEN** the checksum of an artifact to be signed differs from the record in the build manifest
- **THEN** signing aborts and produces no signed artifacts

#### Scenario: Signed package index
- **WHEN** a device with only the release public key installed reads the signed package index
- **THEN** the index signature verifies

#### Scenario: A build of another board
- **WHEN** a build's artifact is named after no board, or its manifest names another board than its artifact does
- **THEN** signing aborts and produces no signed artifacts

#### Scenario: Manifest that names a path outside the build
- **WHEN** a build's manifest names a file by a path that leads out of its directory
- **THEN** signing aborts, produces no signed artifacts, and writes nothing outside its output directory

#### Scenario: A file the manifest does not list
- **WHEN** a build holds a file its manifest does not list
- **THEN** the signed build does not hold it
