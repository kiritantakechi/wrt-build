# Spec Delta

## ADDED Requirements

### Requirement: U-Boot configured without asking
A board's U-Boot and the emulator's SHALL be configured from their configuration fragments without asking anything. A number without a default that a fragment brings up SHALL take zero, as in Linux, unless a later fragment sets it, and neither the merge nor a configuration step after it SHALL wait for an answer.

#### Scenario: A fragment leaves a question for the next
- **WHEN** a fragment brings up a number that has no default, as the second environment copy's flash address when the defconfig keeps the environment in flash
- **THEN** the merge ends within a minute with the number at zero, an `oldconfig` that reads no input ends after it without a change, and a later fragment's value replaces the zero
