# Spec Delta

## Purpose

Defines what each release contains, where it is stored, and how it is organized; distinguishes candidates from stable releases; and ensures that all artifacts in one release come from the same build.

## ADDED Requirements

### Requirement: Publish after signing and drill
After each signing completes and passes the upgrade drill, a Release SHALL be created on GitHub; when the drill fails, a Release MUST NOT be created. The Release contains the signed factory image, the signed single-slot upgrade image, a repository archive containing all packages and kmods from the same build, the build manifest, and checksums for each artifact.

#### Scenario: Inspect Release contents
- **WHEN** a published Release is inspected
- **THEN** it contains the factory image, the upgrade image, the repository archive, the build manifest, and the checksum file, and the vermagic in the manifest matches the kernel version identifier that the kmods in the repository depend on

#### Scenario: Upgrade drill fails
- **WHEN** the signed artifacts do not pass the upgrade drill
- **THEN** no Release is created

### Requirement: Candidates and stable releases
Builds from bump PRs SHALL be published as prereleases (candidates); builds made after merging into the main branch SHALL be published as stable releases.

#### Scenario: PR build
- **WHEN** the build of a bump PR finishes signing
- **THEN** it appears as a prerelease and does not become the latest stable release

#### Scenario: Post-merge build
- **WHEN** the main-branch build after the PR is merged finishes signing
- **THEN** it is published as a stable release and becomes the latest stable release

### Requirement: Artifacts come from one build
If the images and the repository archive come from different build runs (the run identifiers in the build manifest do not match), publishing MUST fail.

#### Scenario: Artifacts mixed from two builds
- **WHEN** the publishing flow receives images and a repository archive from two different builds
- **THEN** publishing fails and no Release is created

### Requirement: Traceable release notes
The Release notes SHALL list the SHAs of the three upstream repositories in the `upstream.lock` used for this build, and the patch queue hash.

#### Scenario: View release notes
- **WHEN** the notes of a Release are opened
- **THEN** the SHAs of openwrt, packages, and luci and the patch queue hash are visible
