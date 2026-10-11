# Spec Delta

## MODIFIED Requirements

### Requirement: Cache keyed on actual inputs
The host stage's cache key SHALL be determined only by the inputs that affect what it builds:
- the contents, as patched, of the tools and toolchain directories of the openwrt repository, of its generic kernel files, from which the toolchain's kernel headers come, of its build files that name the host packages' stamps, and of the Go and Rust directories of the packages feed;
- the board-neutral configuration;
- the build environment;
- the scripts that build and pack the stage.

Every stage SHALL keep a compiler cache for each language it compiles: C and C++, Go, and Rust. Each stage's compiler cache SHALL hold only what that stage's latest build used, so that the caches of all stages fit the repository's cache quota.

#### Scenario: Only the packages feed updated
- **WHEN** the packages feed's SHA in `upstream.lock` changes, but not its Go or Rust directories
- **THEN** the host stage's cache still hits

#### Scenario: Toolchain inputs change
- **WHEN** the tools or toolchain directories of the openwrt repository, its generic kernel files, its build files that name the host packages' stamps, or the Go or Rust directories of the packages feed, change
- **THEN** the host stage's cache is invalidated and rebuilt

#### Scenario: Rebuild from warm compiler caches
- **WHEN** a stage builds sources it has built before, with its compiler cache restored
- **THEN** the caches serve every C, C++, Go and Rust compilation of a source the stage has compiled before, and each language's report shows misses only for sources the build generates anew

#### Scenario: One compiler cache per stage
- **WHEN** a CI run's caches have been pruned
- **THEN** the ref holds one compiler cache for the host stage and one for each board, each holding no entry its stage's latest build left unused

## ADDED Requirements

### Requirement: Main's caches kept whole
The default branch's caches SHALL stay in the repository while other branches run. A run on another branch SHALL save a compiler cache or a download cache only when the repository's caches, with it, stay within the cache quota; otherwise it SHALL go on without saving it. It SHALL always save the toolchain its firmware jobs build on. A run on the default branch SHALL delete the caches of every branch that is merged into it or no longer exists.

#### Scenario: A branch runs while main's caches fill the quota
- **WHEN** a branch's run would need more room than the quota leaves next to the default branch's caches
- **THEN** after the run every cache of the default branch is still there, the branch saved its toolchain and only the caches that fit, and its firmware jobs passed on the caches they restored

#### Scenario: A merged branch
- **WHEN** a branch with caches of its own is merged into the default branch, and the default branch's next run ends
- **THEN** the repository holds no cache of that branch
