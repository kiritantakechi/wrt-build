# Spec Delta

## MODIFIED Requirements

### Requirement: Optimization flags for big.LITTLE cores
Target userspace packages SHALL be compiled with `-O2` and the `-mcpu` of the board they are built for: `cortex-a72.cortex-a53+crypto` for the NanoPi R4S, `cortex-a76.cortex-a55+crypto` for the NanoPi R6S. These two flags MUST come after the default `-Os` and generic CPU flags, so that they take effect. Only packages that explicitly declare an opt-out are exempt.

#### Scenario: Check compile command
- **WHEN** the actual compile command of any target userspace package that has not declared an opt-out is inspected
- **THEN** the command contains `-O2` and the `-mcpu` of the board it is built for, positioned after `-Os`
