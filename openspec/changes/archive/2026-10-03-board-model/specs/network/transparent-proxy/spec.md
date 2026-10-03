# Spec Delta

## MODIFIED Requirements

### Requirement: Optional CPU pinning
dae SHALL be placed by the scheduler by default. An option SHALL pin it to the board's big cores instead: the CPUs with the highest capacity. These are the Cortex-A72 cores cpu4-5 on the NanoPi R4S, and the Cortex-A76 cores cpu4-7 on the NanoPi R6S.

#### Scenario: Enable CPU pinning
- **WHEN** the pinning option is enabled and dae restarts
- **THEN** dae runs only on the CPUs with the highest capacity, and its programs are on the bound interfaces again
