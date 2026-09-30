# Spec Delta

## Purpose

Run the full build automatically, in stages, on GitHub-hosted runners for the public repository, and ensure that the released image and kmod repository come from the same build.

## ADDED Requirements

### Requirement: Staged build within job time limits
CI SHALL split the build into two stages: "host tools and toolchain" and "firmware". Each job MUST finish within the 6-hour limit of GitHub-hosted runners, with 5 hours as an internal target to leave headroom.

#### Scenario: Cold-cache build
- **WHEN** CI runs with no cache at all
- **THEN** all jobs finish within 6 hours and produce the firmware image and the package repository

#### Scenario: Toolchain cache hit
- **WHEN** none of the inputs that affect the toolchain have changed
- **THEN** the toolchain stage reuses the cache directly, and the firmware stage builds on the cached toolchain

### Requirement: Cache keyed on actual inputs
The toolchain stage's cache key SHALL be determined only by the inputs that affect it: the contents of the tools and toolchain directories in the openwrt repository, the toolchain configuration, and the `flake.nix` and `flake.lock` that define the build environment. The firmware stage SHALL use a compiler cache to speed up repeated compilation.

#### Scenario: Only the packages feed updated
- **WHEN** only the packages feed SHA in `upstream.lock` is changed
- **THEN** the toolchain stage cache still hits

#### Scenario: Toolchain inputs change
- **WHEN** the toolchain-related directories of the openwrt repository change
- **THEN** the toolchain cache is invalidated and rebuilt

### Requirement: Build all kmods
The firmware stage SHALL build all kernel module packages and place them in the package repository produced by the same build.

#### Scenario: Repository contains all kmods
- **WHEN** the firmware stage completes
- **THEN** the package repository contains every `kmod-*` package this build can produce, and the kernel version identifier they depend on matches the image kernel

### Requirement: Image and kmods from the same build
Each build SHALL output a manifest that records at least: the build run identifier, the hash of `upstream.lock`, the kernel version identifier (vermagic), and the checksums of the image and the package index. The image and the package repository MUST be handed to the downstream release process as a single unit.

#### Scenario: Complete manifest
- **WHEN** a build finishes successfully
- **THEN** the artifacts include this manifest, and the vermagic it records matches the image kernel and the kmods in the repository

### Requirement: Build stages need no secrets
Build stages in the public repository MUST NOT depend on any repository secret, and MUST NOT have permission to read signing keys.

#### Scenario: CI runs in a fork
- **WHEN** CI runs in a fork that has no secrets configured
- **THEN** both build stages complete successfully and produce unsigned build artifacts
