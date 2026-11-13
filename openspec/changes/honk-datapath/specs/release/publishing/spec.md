## MODIFIED Requirements

### Requirement: Traceable release notes
The Release notes SHALL list the SHA of every repository in the `upstream.lock` used for this build, in the lock's order, and the patch queue hash. Publishing MUST fail when the `upstream.lock` it reads is not the one the builds were made from.

#### Scenario: View release notes
- **WHEN** the notes of a Release are opened
- **THEN** the SHA of every repository `upstream.lock` pins (openwrt, packages, luci and daeuniverse) and the patch queue hash are visible

#### Scenario: A lock that is not the builds'
- **WHEN** publishing runs with an `upstream.lock` other than the one in the builds' manifests
- **THEN** publishing fails and no Release is created
