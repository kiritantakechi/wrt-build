# release/publishing Specification

## Purpose
Defines what each release contains, where it is stored, and how it is organized; distinguishes candidates from stable releases; and ensures that all artifacts in one release come from the same build.

## Requirements

### Requirement: Publish after signing and drill
After each signing completes and every board passes the upgrade drill, a Release SHALL be created on GitHub. When the drill fails on any board, a Release MUST NOT be created. For each board, the Release SHALL contain that board's:
- signed factory image;
- signed single-slot upgrade image;
- repository archive, containing all packages and kmods from the same build;
- build manifest.

Each of these is named after the board's OpenWrt device. One checksum file SHALL cover every asset.

#### Scenario: Inspect Release contents
- **WHEN** a published Release is inspected
- **THEN**:
  - for each board, it contains the factory image, the upgrade image, the repository archive and the build manifest, named after the board's OpenWrt device;
  - it contains the checksum file;
  - the vermagic in each board's manifest matches the kernel version identifier that the kmods in that board's repository depend on

#### Scenario: Upgrade drill fails
- **WHEN** the signed artifacts of any board do not pass the upgrade drill
- **THEN** no Release is created

#### Scenario: A board missing
- **WHEN** the publishing flow lacks the signed build of a board
- **THEN** publishing fails and no Release is created

### Requirement: Candidates and stable releases
Builds from bump PRs SHALL be published as prereleases (candidates); builds made after merging into the main branch SHALL be published as stable releases.

#### Scenario: PR build
- **WHEN** the build of a bump PR finishes signing
- **THEN** it appears as a prerelease and does not become the latest stable release

#### Scenario: Post-merge build
- **WHEN** the main-branch build after the PR is merged finishes signing
- **THEN** it is published as a stable release and becomes the latest stable release

### Requirement: Artifacts come from one build
Each board's images and repository archive SHALL come from one build of that board: if their run identifiers in the build manifest do not match, publishing MUST fail. The builds of all boards in a Release SHALL come from the same sources: if their manifests differ in the `upstream.lock` hash, the patch queue hash or the upstream commit, publishing MUST fail.

#### Scenario: Artifacts mixed from two builds
- **WHEN** the publishing flow receives images and a repository archive from two different builds
- **THEN** publishing fails and no Release is created

#### Scenario: Boards built from different sources
- **WHEN** the publishing flow receives the builds of two boards made from different sources
- **THEN** publishing fails and no Release is created

### Requirement: Traceable release notes
The Release notes SHALL list the SHAs of the three upstream repositories in the `upstream.lock` used for this build, and the patch queue hash.

#### Scenario: View release notes
- **WHEN** the notes of a Release are opened
- **THEN** the SHAs of openwrt, packages, and luci and the patch queue hash are visible
