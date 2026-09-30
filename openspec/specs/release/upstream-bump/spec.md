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
A bump PR SHALL carry a required check, "upgrade drill". The drill runs in the emulator: boot the factory image of the latest stable release, push a test configuration, sync this signed candidate, write it to the inactive slot with the upgrade command, and reboot. The check passes only when the new slot passes the health check and is confirmed, and the configuration is still present. When the check does not pass, the PR MUST NOT be merged.

#### Scenario: Candidate fails the health check
- **WHEN** the candidate boots in the drill and never passes the health check
- **THEN** the device in the drill automatically returns to its original slot, the check fails, and the PR cannot be merged

#### Scenario: Drill passes
- **WHEN** the candidate passes the health check in the drill and is confirmed, and all pushed configuration is still present
- **THEN** the check passes and the PR can be merged
