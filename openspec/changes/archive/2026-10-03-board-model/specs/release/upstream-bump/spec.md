# Spec Delta

## MODIFIED Requirements

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
