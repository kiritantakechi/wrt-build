# Spec Delta

## MODIFIED Requirements

### Requirement: Signing targets
For every board's build, the signing job SHALL sign all package indexes with the release apk key, and the factory image and the upgrade image with the release firmware key. Before signing, it MUST verify that these artifacts match the checksums in their board's build manifest.

#### Scenario: Artifact does not match the manifest
- **WHEN** the checksum of an artifact to be signed differs from the record in the build manifest
- **THEN** signing aborts and produces no signed artifacts

#### Scenario: Signed package index
- **WHEN** a device with only the release public key installed reads the signed package index
- **THEN** the index signature verifies
