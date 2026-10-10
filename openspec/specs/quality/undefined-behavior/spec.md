# quality/undefined-behavior Specification

## Purpose
Find the undefined behavior in the C and C++ code the image ships, which aggressive optimization turns into wrong code, and keep it fixed in the code rather than masked by compiler flags.

## Requirements

### Requirement: UB-indicative warnings fixed or reviewed
Every warning that the build of a package the image ships emits for one of the UB-indicative options SHALL either be fixed by a patch, or be reviewed in the register as not undefined behavior, with the reason. The register MUST NOT keep an entry that no warning of the build matches. The UB-indicative options are `-Waggressive-loop-optimizations`, `-Warray-bounds`, `-Wstringop-overflow`, `-Wstringop-overread`, `-Wuse-after-free`, `-Wdangling-pointer`, `-Wfree-nonheap-object`, `-Wuninitialized`, `-Wmaybe-uninitialized`, `-Wshift-count-overflow`, `-Wshift-count-negative`, `-Wshift-negative-value`, `-Wstrict-aliasing` and `-Waddress-of-packed-member`.

#### Scenario: Unreviewed warning
- **WHEN** a package the image ships emits a UB-indicative warning that the register does not review
- **THEN** the check fails, and names the package, the option and the source location of the warning

#### Scenario: Stale review
- **WHEN** an entry of the register matches no warning of the build
- **THEN** the check fails, and names the entry

### Requirement: Undefined behavior traps under UBSan
A build of the `ubsan` profile SHALL instrument every target package with UBSan in trap mode, except the toolchain's libraries and the kernel. A trap while the system tests run SHALL fail a test and name the process that trapped: the test during which it trapped, or, for a trap in a fixture outside every test, the last test that used the fixture.

#### Scenario: Trap during a system test
- **WHEN** a process of a `ubsan` build traps on undefined behavior while a system test runs
- **THEN** that test fails, and names the process

### Requirement: No global masking of undefined behavior
The compiler flags shared by all target packages and the kernel SHALL NOT contain an option that defines away a class of undefined behavior instead of fixing it: `-fwrapv`, `-fno-strict-overflow`, `-fno-strict-aliasing`, `-fno-delete-null-pointer-checks` or `-fno-aggressive-loop-optimizations`. A package keeps such an option only where its own build adds it.

#### Scenario: Check the shared flags
- **WHEN** the compiler flags a board's build shares across the target packages and adds to the kernel are inspected
- **THEN** none of the masking options is among them
