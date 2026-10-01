# Spec Delta

## MODIFIED Requirements

### Requirement: Optimization flags for big.LITTLE cores
Target userspace packages SHALL be compiled with `-O3` and the `-mcpu` of the board they are built for: `cortex-a72.cortex-a53+crypto` for the NanoPi R4S, `cortex-a76.cortex-a55+crypto` for the NanoPi R6S. These two flags MUST come after the default `-Os` and generic CPU flags, so that they take effect. Only packages that explicitly declare an opt-out are exempt.

#### Scenario: Check compile command
- **WHEN** the actual compile command of any target userspace package that has not declared an opt-out is inspected
- **THEN** the command contains `-O3` and the `-mcpu` of the board it is built for, positioned after `-Os`

## ADDED Requirements

### Requirement: Kernel at its supported optimization level
The kernel and its modules SHALL be compiled with `-O2`, the optimization level upstream Linux supports, whatever level the target packages use, and with the `-mcpu` of the board they are built for.

#### Scenario: Check the kernel's flags
- **WHEN** the flags a board's build adds to the kernel's compiler flags are inspected
- **THEN** the last optimization flag among them is `-O2`, and they carry the board's `-mcpu`

### Requirement: No relaxed floating-point semantics
No target package and no kernel code SHALL be compiled with an option that relaxes IEEE floating-point semantics: `-Ofast`, `-ffast-math`, `-funsafe-math-optimizations`, `-ffinite-math-only`, `-fno-signed-zeros`, `-fno-trapping-math` or `-fassociative-math`.

#### Scenario: Check for relaxed floating point
- **WHEN** the compiler flags of the target packages and of the kernel of a board's build are inspected
- **THEN** none of the relaxing options is among them
