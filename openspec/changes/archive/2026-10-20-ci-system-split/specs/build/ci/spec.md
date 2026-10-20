# Spec Delta

## ADDED Requirements

### Requirement: System tests within job time limits
CI SHALL run every system test of a board exactly once per run, split into jobs that each finish within their time limit on a usual runner with room for one at least 1.8 times slower.

#### Scenario: Every test in one job
- **WHEN** the paths of a board's system test jobs are taken together
- **THEN** each test module of the suite is selected by exactly one of them
