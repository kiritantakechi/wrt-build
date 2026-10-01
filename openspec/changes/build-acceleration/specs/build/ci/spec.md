# Spec Delta

## MODIFIED Requirements

### Requirement: Staged build within job time limits
CI SHALL split the build into two stages. The host stage SHALL build, once for every board, the host tools and every toolchain the firmware needs: the cross toolchain, and the Go and Rust host toolchains. The firmware stage SHALL build a board's target code on them, once per board, and MUST NOT compile any of them. Each job MUST finish within the 6-hour limit of GitHub-hosted runners, with 5 hours as an internal target to leave headroom.

#### Scenario: Cold-cache build
- **WHEN** CI runs with no cache at all
- **THEN** all jobs finish within 6 hours and produce the firmware image and the package repository

#### Scenario: Toolchain cache hit
- **WHEN** none of the inputs that affect the host stage have changed
- **THEN** the host stage reuses its cache directly, and each firmware job, in its own fresh checkout, builds on the restored toolchains without compiling any part of them

### Requirement: Cache keyed on actual inputs
The host stage's cache key SHALL be determined only by the inputs that affect what it builds:
- the contents, as patched, of the tools and toolchain directories of the openwrt repository and of the Go and Rust directories of the packages feed;
- the board-neutral configuration;
- the build environment;
- the scripts that build and pack the stage.

Every stage SHALL keep a compiler cache for each language it compiles: C and C++, Go, and Rust. Each stage's compiler cache SHALL hold only what that stage's latest build used, so that the caches of all stages fit the repository's cache quota.

#### Scenario: Only the packages feed updated
- **WHEN** the packages feed's SHA in `upstream.lock` changes, but not its Go or Rust directories
- **THEN** the host stage's cache still hits

#### Scenario: Toolchain inputs change
- **WHEN** the tools or toolchain directories of the openwrt repository, or the Go or Rust directories of the packages feed, change
- **THEN** the host stage's cache is invalidated and rebuilt

#### Scenario: Rebuild from warm compiler caches
- **WHEN** a stage builds sources it has built before, with its compiler cache restored
- **THEN** the cache serves every cacheable C, C++, Go and Rust compilation, and the build's report of each language's cache shows no miss

#### Scenario: One compiler cache per stage
- **WHEN** a CI run's caches have been pruned
- **THEN** the ref holds one compiler cache for the host stage and one for each board, each holding no entry its stage's latest build left unused
