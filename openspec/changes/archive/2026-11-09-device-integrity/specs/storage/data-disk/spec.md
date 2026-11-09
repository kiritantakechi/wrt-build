# Spec Delta

## MODIFIED Requirements

### Requirement: Periodic read-only snapshots
`@containers` and `@shares` SHALL each get a daily read-only snapshot, stored in `.snapshots`. Each SHALL keep the snapshots of the 7 most recent days on which it got one, however long ago those days are, and no other. The administrator SHALL be able to take a snapshot manually at any time. The administrator SHALL be able to restore a single file from a snapshot.

#### Scenario: Expired snapshots are pruned
- **WHEN** the system has been running for more than 8 days
- **THEN** `.snapshots` retains only the 7 most recent daily snapshots for each of the two subvolumes

#### Scenario: Snapshots after a long time off
- **WHEN** the system ran for 7 days, then stayed off for 10, and its daily job runs once after it is back
- **THEN** `.snapshots` retains, for each of the two subvolumes, the snapshot of the day it came back and those of the 6 most recent days before

#### Scenario: Manual snapshot
- **WHEN** the administrator runs the manual snapshot command
- **THEN** a read-only snapshot with the current timestamp appears in `.snapshots`

#### Scenario: Restore a file from a snapshot
- **WHEN** a file in a share is deleted after a snapshot, and the administrator restores it from the snapshot as documented
- **THEN** the restored file matches its content before deletion
