# Spec Delta

## MODIFIED Requirements

### Requirement: UB-indicative warnings fixed or reviewed
Every warning that the build of a package the image ships emits for one of the UB-indicative options SHALL either be fixed by a patch, or be reviewed in the register as not undefined behavior, with the reason. The register MUST NOT keep an entry that no warning of the build matches. The UB-indicative options are `-Waggressive-loop-optimizations`, `-Warray-bounds`, `-Wstringop-overflow`, `-Wstringop-overread`, `-Wuse-after-free`, `-Wdangling-pointer`, `-Wfree-nonheap-object`, `-Wuninitialized`, `-Wmaybe-uninitialized`, `-Wshift-count-overflow`, `-Wshift-count-negative`, `-Wshift-negative-value`, `-Wstrict-aliasing` and `-Waddress-of-packed-member`.

#### Scenario: Unreviewed warning
- **WHEN** a package the image ships emits a UB-indicative warning that the register does not review
- **THEN** the check fails, and names the package, the option and the source location of the warning

#### Scenario: Stale review
- **WHEN** an entry of the register matches no warning of the build
- **THEN** the check fails, and names the entry

#### Scenario: Package packed again without a compile
- **WHEN** an incremental build packs a package again without compiling it, as when its package is gone from the output directory or OpenWrt's packaging rules changed
- **THEN** the warnings of the package's last compile still count in the check
