# firmware/toolchain Specification

## Purpose
Define the compiler version, linker, and optimization flags for target packages, so that each board's system is optimized for its big.LITTLE CPU cores, built with one toolchain that every board shares.

## Requirements

### Requirement: Target toolchain version
The target toolchain SHALL use GCC 15 and musl libc.

#### Scenario: Check toolchain version
- **WHEN** the version of the built target cross compiler is inspected
- **THEN** the GCC major version is 15 and the C library is musl

### Requirement: Optimization flags for big.LITTLE cores
Target userspace packages SHALL be compiled with `-O2` and the `-mcpu` of the board they are built for: `cortex-a72.cortex-a53+crypto` for the NanoPi R4S, `cortex-a76.cortex-a55+crypto` for the NanoPi R6S. These two flags MUST come after the default `-Os` and generic CPU flags, so that they take effect. Only packages that explicitly declare an opt-out are exempt.

#### Scenario: Check compile command
- **WHEN** the actual compile command of any target userspace package that has not declared an opt-out is inspected
- **THEN** the command contains `-O2` and the `-mcpu` of the board it is built for, positioned after `-Os`

### Requirement: LTO, mold, and gc-sections by default
Target packages SHALL use link-time optimization (LTO), the mold linker, and garbage collection of unused sections (gc-sections) by default. A package that fails to build with these options MUST opt out of the relevant option in its own build definition, rather than disabling it globally.

#### Scenario: Package incompatible with LTO
- **WHEN** a package fails to build under LTO
- **THEN** only that package disables LTO, the opt-out is recorded in its package definition or the corresponding patch, and all other packages still use LTO

### Requirement: Optimization through configuration only
All of the toolchain and optimization settings above SHALL be implemented through build configuration, and MUST NOT modify the upstream build system file that defines the default compiler flags (`include/target.mk`).

#### Scenario: Audit patch queue
- **WHEN** the files modified by the openwrt patch queue are listed
- **THEN** they do not include `include/target.mk`
