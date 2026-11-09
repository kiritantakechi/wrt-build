# Spec Delta

## MODIFIED Requirements

### Requirement: Candidates and stable releases
Builds from bump PRs SHALL be published as prereleases (candidates); builds made after merging into the main branch SHALL be published as stable releases. A Release SHALL be published only from the commit its branch holds when publishing starts, and its tag SHALL point at that commit: a run of a commit its branch has moved past, a re-run among them, MUST NOT publish.

#### Scenario: PR build
- **WHEN** the build of a bump PR finishes signing
- **THEN** it appears as a prerelease and does not become the latest stable release

#### Scenario: Post-merge build
- **WHEN** the main-branch build after the PR is merged finishes signing
- **THEN** it is published as a stable release and becomes the latest stable release

#### Scenario: A run its branch has moved past
- **WHEN** a run's publishing starts after its branch has moved to a newer commit
- **THEN** publishing fails, naming both commits, and no Release is created

#### Scenario: Tag of a Release
- **WHEN** a Release is published
- **THEN** its tag points at the commit that was built

### Requirement: Artifacts come from one build
Each board's images and repository archive SHALL come from one build of that board: if their run identifiers in the build manifest do not match, publishing MUST fail. The builds of all boards in a Release SHALL come from the same sources: if their manifests differ in the `upstream.lock` hash, the patch queue hash, the upstream commit or the commit of this repository they were built from, publishing MUST fail.

#### Scenario: Artifacts mixed from two builds
- **WHEN** the publishing flow receives images and a repository archive from two different builds
- **THEN** publishing fails and no Release is created

#### Scenario: Boards built from different sources
- **WHEN** the publishing flow receives the builds of two boards made from different sources
- **THEN** publishing fails and no Release is created

#### Scenario: Boards built from different commits of this repository
- **WHEN** the publishing flow receives the builds of two boards made from the same upstream sources but different commits of this repository
- **THEN** publishing fails and no Release is created

### Requirement: Traceable release notes
The Release notes SHALL list the SHAs of the three upstream repositories in the `upstream.lock` used for this build, and the patch queue hash. Publishing MUST fail when the `upstream.lock` it reads is not the one the builds were made from.

#### Scenario: View release notes
- **WHEN** the notes of a Release are opened
- **THEN** the SHAs of openwrt, packages, and luci and the patch queue hash are visible

#### Scenario: A lock that is not the builds'
- **WHEN** publishing runs with an `upstream.lock` other than the one in the builds' manifests
- **THEN** publishing fails and no Release is created
