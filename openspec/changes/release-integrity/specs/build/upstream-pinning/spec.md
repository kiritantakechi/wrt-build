# Spec Delta

## MODIFIED Requirements

### Requirement: Ordered patches, stop on failure
All modifications to upstream SHALL be stored in the repository as patch files, in one directory per upstream repository, and applied in file name order. When any patch does not apply cleanly, the build MUST abort and report that patch's file name. The commit the patches make SHALL depend on nothing but `upstream.lock` and the patch files: neither the user's nor the system's git configuration changes it.

#### Scenario: Patch conflict
- **WHEN** after an upstream update, a patch no longer applies cleanly
- **THEN** the build aborts and names the conflicting patch file, without generating configuration or producing anything

#### Scenario: All patches apply
- **WHEN** all patches apply cleanly
- **THEN** the resulting source tree depends only on `upstream.lock` and the patch files themselves, not on when the patches were applied

#### Scenario: A git configuration of the user's own
- **WHEN** the patches are applied by a user whose git configuration fixes whitespace on apply and signs every commit
- **THEN** the patched commit is the one a user without that configuration gets
