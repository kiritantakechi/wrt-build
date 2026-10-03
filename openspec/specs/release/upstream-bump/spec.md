# release/upstream-bump Specification

## Purpose
Defines the weekly cadence for tracking upstream main: a bot opens a PR to update the lock file, CI builds and signs a candidate, and the PR is merged only after the candidate passes an upgrade drill in the emulator.

## Requirements

### Requirement: Weekly automated PR
The bot SHALL check the main branches of openwrt, packages, and luci once a week. When there are updates, it SHALL open a PR that updates `upstream.lock`, with the old and new SHAs and a summary of the upstream commits in the PR description. When none of the three repositories has updates, it MUST NOT open a PR.

#### Scenario: Upstream has updates
- **WHEN** the weekly check runs and upstream has new commits
- **THEN** a PR that updates `upstream.lock` appears, with the old and new SHAs and a summary of the upstream commits in its description

#### Scenario: Upstream has no updates
- **WHEN** the weekly check runs but none of the three repositories has new commits
- **THEN** no PR is opened

### Requirement: Fail clearly when patches do not apply
If patches fail to apply after a bump, the PR's CI SHALL fail and name the conflicting patch file in the result.

#### Scenario: BBRv3 patch conflict
- **WHEN** a BBRv3 patch fails to apply after a bump
- **THEN** the PR check fails, and the failure message names the conflicting patch file

### Requirement: Merge only after the upgrade drill passes
A bump PR SHALL carry a required check, "upgrade drill". The drill runs in the emulator, for every board:
1. boot the factory image of the board's latest stable release, as the board's manifest in that release names it and matching it; while no stable release carries the board, the candidate's own factory image;
2. push a test configuration;
3. sync this signed candidate;
4. write it to the inactive slot with the upgrade command, and reboot.

The check passes only when, on every board, the new slot passes the health check and is confirmed, and the configuration is still present. When the check does not pass, the PR MUST NOT be merged.

#### Scenario: Candidate fails the health check
- **WHEN** the candidate boots in the drill of a board and never passes the health check
- **THEN** that board's device in the drill automatically returns to its original slot, the check fails, and the PR cannot be merged

#### Scenario: Drill passes
- **WHEN** the candidate passes the health check in every board's drill and is confirmed, and all pushed configuration is still present
- **THEN** the check passes and the PR can be merged

#### Scenario: Drill base of each board
- **WHEN** the latest stable release carries one board and not another, and the drill runs for both
- **THEN** the first board's drill boots the factory image its manifest in that release names, and the other board's boots the candidate's own

#### Scenario: Drill base cannot be had
- **WHEN** the latest stable release cannot be looked up, or its factory image of a board does not match the board's manifest
- **THEN** that board's drill fails, rather than start from another image
