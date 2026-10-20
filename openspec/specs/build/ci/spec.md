# build/ci Specification

## Purpose
Run the full build automatically, in stages, on GitHub-hosted runners for the public repository, and ensure that the released image and kmod repository come from the same build.

## Requirements

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

### Requirement: Build all kmods
The firmware stage SHALL build all kernel module packages and place them in the package repository produced by the same build.

#### Scenario: Repository contains all kmods
- **WHEN** the firmware stage completes
- **THEN** the package repository contains every `kmod-*` package this build can produce, and the kernel version identifier they depend on matches the image kernel

### Requirement: Image and kmods from the same build
Each build SHALL output a manifest that records at least: the board it was built for and the board's OpenWrt device, the build run identifier, the hash of `upstream.lock`, the kernel version identifier (vermagic), and the checksums of the image and the package index. The image and the package repository MUST be handed to the downstream release process as a single unit.

#### Scenario: Complete manifest
- **WHEN** a build finishes successfully
- **THEN** the artifacts include this manifest, it names the board that was built and its device, and the vermagic it records matches the image kernel and the kmods in the repository

### Requirement: Build stages need no secrets
Build stages in the public repository MUST NOT depend on any repository secret, and MUST NOT have permission to read signing keys.

#### Scenario: CI runs in a fork
- **WHEN** CI runs in a fork that has no secrets configured
- **THEN** both build stages complete successfully and produce unsigned build artifacts

### Requirement: Main's caches kept whole
The default branch's caches SHALL stay in the repository while other branches run. A run on another branch SHALL save a compiler cache or a download cache only when the repository's caches, with it, stay within the cache quota; otherwise it SHALL go on without saving it. It SHALL always save the toolchain its firmware jobs build on. A run on the default branch SHALL delete the caches of every branch that is merged into it or no longer exists.

#### Scenario: A branch runs while main's caches fill the quota
- **WHEN** a branch's run would need more room than the quota leaves next to the default branch's caches
- **THEN** after the run every cache of the default branch is still there, the branch saved its toolchain and only the caches that fit, and its firmware jobs passed on the caches they restored

#### Scenario: A merged branch
- **WHEN** a branch with caches of its own is merged into the default branch, and the default branch's next run ends
- **THEN** the repository holds no cache of that branch

### Requirement: System tests within job time limits
CI SHALL run every system test of a board exactly once per run, split into jobs that each finish within their time limit on a usual runner with room for one at least 1.8 times slower.

#### Scenario: Every test in one job
- **WHEN** the paths of a board's system test jobs are taken together
- **THEN** each test module of the suite is selected by exactly one of them
