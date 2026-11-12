## MODIFIED Requirements

### Requirement: Upstream sources pinned to commits
The four upstream repositories, openwrt, packages, luci, and daeuniverse's OpenWrt feed (daeuniverse), SHALL be fetched by the URL and commit SHA recorded in `upstream.lock`. Builds MUST NOT use a branch HEAD or the current target of a tag.

#### Scenario: Same lock yields same sources
- **WHEN** sources are fetched at different times on different machines from the same `upstream.lock`
- **THEN** the commit SHAs checked out for all four repositories match the lock

#### Scenario: Feeds configuration pinned to commits
- **WHEN** the feeds configuration is generated
- **THEN** every feed entry carries the commit SHA from the lock and references no branch name
