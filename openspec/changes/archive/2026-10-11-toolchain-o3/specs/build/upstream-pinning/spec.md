# Spec Delta

## ADDED Requirements

### Requirement: Every patch states its upstream status
Every patch file in the repository SHALL state its upstream status in an `Upstream-Status` trailer of its own, in OpenEmbedded's vocabulary:
- `Pending`: meant for upstream, not submitted;
- `Submitted [<where>]`: submitted, under review;
- `Backport [<source>]`: taken from upstream or another primary source;
- `Inappropriate [<reason>]`: project-specific.

This covers the patch series applied to the sources, the patches of the feed's own packages, QEMU's patches, and the patches prepared for upstream but not carried. Every `Pending` or `Submitted` patch SHALL have a write-up in the patch documentation, and every write-up SHALL name a patch that exists.

#### Scenario: Patch without a status
- **WHEN** a patch file has no `Upstream-Status` trailer, or one outside the vocabulary
- **THEN** the check fails, and names the patch

#### Scenario: Patch meant for upstream without a write-up
- **WHEN** a `Pending` or `Submitted` patch has no write-up in the patch documentation
- **THEN** the check fails, and names the patch

#### Scenario: Write-up without a patch
- **WHEN** the patch documentation has a write-up for a patch that no file in the repository holds
- **THEN** the check fails, and names the write-up
