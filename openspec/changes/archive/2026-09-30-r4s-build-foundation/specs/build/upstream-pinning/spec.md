# Spec Delta

## Purpose

Ensure that the upstream sources, feeds, and patches used by each build are determined entirely by repository contents and are reproducible, and that any broken patch surfaces immediately, before the build starts.

## ADDED Requirements

### Requirement: Upstream sources pinned to commits
The three upstream repositories, openwrt, packages, and luci, SHALL be fetched by the URL and commit SHA recorded in `upstream.lock`. Builds MUST NOT use a branch HEAD or the current target of a tag.

#### Scenario: Same lock yields same sources
- **WHEN** sources are fetched at different times on different machines from the same `upstream.lock`
- **THEN** the commit SHAs checked out for all three repositories match the lock

#### Scenario: Feeds configuration pinned to commits
- **WHEN** the feeds configuration is generated
- **THEN** every feed entry carries the commit SHA from the lock and references no branch name

### Requirement: Ordered patches, stop on failure
All modifications to upstream SHALL be stored in the repository as patch files, in one directory per upstream repository, and applied in file name order. When any patch does not apply cleanly, the build MUST abort and report that patch's file name.

#### Scenario: Patch conflict
- **WHEN** after an upstream update, a patch no longer applies cleanly
- **THEN** the build aborts and names the conflicting patch file, without generating configuration or producing anything

#### Scenario: All patches apply
- **WHEN** all patches apply cleanly
- **THEN** the resulting source tree depends only on `upstream.lock` and the patch files themselves, not on when the patches were applied

### Requirement: No remote scripts or in-place upstream edits
The build MUST NOT download scripts or patches from the network to execute or apply, and MUST NOT modify upstream files with in-place text substitution (for example `sed -i`). Upstream package source archives SHALL be fetched through hash-verified downloads.

#### Scenario: Audit build scripts
- **WHEN** all build scripts and CI workflows in the repository are inspected
- **THEN** no command is found that downloads and executes or applies remote scripts or patches, and no in-place text substitution on the upstream source tree is found

### Requirement: Reproducible build timestamp
The `SOURCE_DATE_EPOCH` used by the build SHALL equal the commit time of the openwrt commit in `upstream.lock`, regardless of when the patches were applied.

#### Scenario: Same lock built at different times
- **WHEN** the same `upstream.lock` and the same patch set are built once each on different dates
- **THEN** both builds use the same `SOURCE_DATE_EPOCH`, and the build date recorded in the image is also the same
