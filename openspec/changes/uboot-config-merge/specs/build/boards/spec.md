# Spec Delta

## ADDED Requirements

### Requirement: U-Boot fragments merge without asking
A board's U-Boot and the emulator's SHALL merge their configuration fragments without asking anything. A symbol without a default that a fragment brings up SHALL stay unset, for a later fragment or none to settle, and the merge SHALL end.

#### Scenario: A fragment leaves a question for the next
- **WHEN** a fragment brings up a symbol that has no default, as the second environment copy's flash address when the defconfig keeps the environment in flash
- **THEN** the merge ends within a minute, and the symbol stays unset
