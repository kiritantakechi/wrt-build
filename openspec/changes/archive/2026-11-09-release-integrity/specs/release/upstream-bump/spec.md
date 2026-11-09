# Spec Delta

## MODIFIED Requirements

### Requirement: Weekly automated PR
The bot SHALL check the main branches of openwrt, packages, and luci once a week. When there are updates, it SHALL open a PR that updates `upstream.lock`, with the old and new SHAs and a summary of the upstream commits in the PR description. When none of the three repositories has updates, it MUST NOT open a PR. It SHALL start the bump branch's check and build before it opens the PR, so that a PR that cannot be opened leaves them running and fails the bot's run naming why. A bump run again on a day whose branch exists MUST NOT change the branch, and SHALL open the PR that branch still lacks.

#### Scenario: Upstream has updates
- **WHEN** the weekly check runs and upstream has new commits
- **THEN** a PR that updates `upstream.lock` appears, with the old and new SHAs and a summary of the upstream commits in its description

#### Scenario: Upstream has no updates
- **WHEN** the weekly check runs but none of the three repositories has new commits
- **THEN** no PR is opened

#### Scenario: The PR cannot be opened
- **WHEN** the bot pushes a bump branch but may not open PRs
- **THEN** the branch's check and build run, and the bot's run fails, saying that it may not open the PR

#### Scenario: Bump run again
- **WHEN** the bot runs again on a day whose bump branch exists, with commits on it the bot did not make
- **THEN** the branch keeps its commits, and the bot opens its PR if it has none

### Requirement: Merge only after the upgrade drill passes
A bump PR SHALL carry a required check, "upgrade drill". The drill runs in the emulator, for every board:
1. boot the factory image of the board's latest stable release, as the board's manifest in that release names it and matching it; while no stable release carries the board, the candidate's own factory image;
2. push a test configuration;
3. sync this signed candidate;
4. write it to the inactive slot with the upgrade command, and reboot.

The check passes only when, on every board, the new slot passes the health check and is confirmed, and the configuration is still present. When the check does not pass, the PR MUST NOT be merged. While release signing is set up, the check MUST fail in a run of a bump PR's pull request event, which cannot sign: only the bump branch's own run, which drills, passes it.

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

#### Scenario: The PR's own run of a bump
- **WHEN** release signing is set up and a commit is pushed to a bump PR, which runs the build for the PR
- **THEN** that run's upgrade-drill check fails, naming the bump branch's own run as the one that drills
