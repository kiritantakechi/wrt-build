# Spec Delta

## ADDED Requirements

### Requirement: The router back at its snapshot
When the harness returns the router to its post-boot snapshot, the router SHALL answer the runner at once, and its clock SHALL be the runner's within two seconds, whatever the router went through since the snapshot, a boot into failsafe mode on another link-layer address included.

#### Scenario: Back from failsafe mode
- **WHEN** the router has booted into failsafe mode, and the harness returns it to its snapshot
- **THEN** the return takes seconds, not the half minute a stale link-layer address costs, and the router's clock is within two seconds of the runner's
