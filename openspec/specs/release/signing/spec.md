# release/signing Specification

## Purpose
Defines the isolation, approval, and targets of release signing, and requires devices to trust only the release public keys. This way, even if third-party code executed during the build is poisoned, it cannot obtain a key that can impersonate the publisher long term.

## Requirements

### Requirement: Build and signing are isolated
Signing SHALL happen in a separate job. That job runs only signing tools pinned by the repository and built from first-party sources, and MUST NOT execute any package build scripts or third-party dependencies. The build job MUST NOT have access to the signing keys.

#### Scenario: Check build job permissions
- **WHEN** the build job's definition and runtime environment are inspected
- **THEN** they reference no signing keys, and no signing key is readable at runtime

#### Scenario: Check what the signing job runs
- **WHEN** the signing job's execution log is inspected
- **THEN** only the pinned signing tools ran, verifying and signing the downloaded artifacts, and no package was compiled

### Requirement: Every signing requires manual approval
Each signing SHALL require explicit approval from a repository maintainer. Without approval, signed artifacts MUST NOT be produced.

#### Scenario: No approval
- **WHEN** the build completes and the maintainer does not approve signing
- **THEN** the signing job stays in the waiting state and produces no signed artifacts

### Requirement: Signing targets
For every board's build, the signing job SHALL sign all package indexes with the release apk key, and the factory image and the upgrade image with the release firmware key. Before signing, it MUST verify that these artifacts match the checksums in their board's build manifest.

#### Scenario: Artifact does not match the manifest
- **WHEN** the checksum of an artifact to be signed differs from the record in the build manifest
- **THEN** signing aborts and produces no signed artifacts

#### Scenario: Signed package index
- **WHEN** a device with only the release public key installed reads the signed package index
- **THEN** the index signature verifies

### Requirement: Devices trust only release keys
The firmware image SHALL contain only the release public keys as the trust anchor for packages and firmware. It MUST NOT contain keys generated temporarily during the build, and MUST NOT contain the official OpenWrt public keys.

#### Scenario: Check trust anchors in the image
- **WHEN** `/etc/apk/keys` and the firmware signing public key directory in the image are listed
- **THEN** they contain only this project's release public keys

#### Scenario: Index signed with another key
- **WHEN** the device reads a package index signed with another key
- **THEN** the package manager refuses to use the index

### Requirement: Key rotation support
The trust anchor SHALL support holding several release public keys at once, so that during a key rotation, artifacts signed by either the old or the new key are accepted throughout the transition period.

#### Scenario: Rotation transition period
- **WHEN** the image contains both the old and the new release public keys
- **THEN** package indexes signed with either key pass verification
