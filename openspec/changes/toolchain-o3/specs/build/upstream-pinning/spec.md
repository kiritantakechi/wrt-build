# Spec Delta

## ADDED Requirements

### Requirement: Every patch registered
Every patch file in the repository SHALL have exactly one entry in the patch register:
- the patch series applied to the sources;
- the patches of the feed's own packages;
- QEMU's patches;
- the patches prepared for upstream but not carried.

The entry names the patch's purpose, its kind (project-specific, meant for upstream, or a backport) and its upstream status. The register MUST NOT list a patch that does not exist.

#### Scenario: Patch without an entry
- **WHEN** a patch file is added to the repository without an entry in the register
- **THEN** the check fails, and names the patch

#### Scenario: Entry without a patch
- **WHEN** the register lists a patch that no file in the repository holds
- **THEN** the check fails, and names the entry
