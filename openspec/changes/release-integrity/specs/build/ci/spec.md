# Spec Delta

## MODIFIED Requirements

### Requirement: Image and kmods from the same build
Each build SHALL output a manifest that records at least: the board it was built for and the board's OpenWrt device, the build run identifier, the hash of `upstream.lock`, the commit of this repository it was built from, the kernel version identifier (vermagic), and the checksum of every file it hands on, each named by its path in the build: the images, the package indexes and the packages among them. The image and the package repository MUST be handed to the downstream release process as a single unit.

#### Scenario: Complete manifest
- **WHEN** a build finishes successfully
- **THEN** the artifacts include this manifest, it names the board that was built and its device, it lists every other file of the artifacts with its checksum, and the vermagic it records matches the image kernel and the kmods in the repository

### Requirement: Cache keyed on actual inputs
The host stage's cache key SHALL be determined only by the inputs that affect what it builds:
- the contents, as patched, of the tools and toolchain directories of the openwrt repository, of its generic kernel files, from which the toolchain's kernel headers come, of its build files that name the host packages' stamps, and of the Go and Rust directories of the packages feed;
- the definition of the target and subtarget the boards select: the makefiles that name their architecture, CPU type, features and kernel version;
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

#### Scenario: Kernel version of the target changes
- **WHEN** the boards' target selects another kernel version, and nothing else of the key's inputs changes
- **THEN** the host stage's cache is invalidated and rebuilt

#### Scenario: A device added to the target
- **WHEN** the boards' target gains a device, and nothing else of the key's inputs changes
- **THEN** the host stage's cache still hits

#### Scenario: Rebuild from warm compiler caches
- **WHEN** a stage builds sources it has built before, with its compiler cache restored
- **THEN** the caches serve every C, C++, Go and Rust compilation of a source the stage has compiled before, and each language's report shows misses only for sources the build generates anew

#### Scenario: One compiler cache per stage
- **WHEN** a CI run's caches have been pruned
- **THEN** the ref holds one compiler cache for the host stage and one for each board, each holding no entry its stage's latest build left unused

#### Scenario: Stage names with a hyphen
- **WHEN** a ref holds compiler caches of the stages `r6s` and `r6s-plus`, and its caches are pruned
- **THEN** the newest compiler cache of each stage stays

### Requirement: Main's caches kept whole
The default branch's caches SHALL stay in the repository while other branches run. A run on another branch SHALL save a compiler cache or a download cache only when the repository's caches, with it and with what the run's other jobs may save at the same time, stay within the cache quota; otherwise it SHALL go on without saving it. It SHALL always save the toolchain its firmware jobs build on. A download cache SHALL be saved only by a job whose downloads all finished. A run on the default branch SHALL delete the caches of every branch that is merged into it or no longer exists, and of every pull request that is closed.

#### Scenario: A branch runs while main's caches fill the quota
- **WHEN** a branch's run would need more room than the quota leaves next to the default branch's caches
- **THEN** after the run every cache of the default branch is still there, the branch saved its toolchain and only the caches that fit, and its firmware jobs passed on the caches they restored

#### Scenario: A merged branch
- **WHEN** a branch with caches of its own is merged into the default branch, and the default branch's next run ends
- **THEN** the repository holds no cache of that branch

#### Scenario: A closed pull request
- **WHEN** a pull request with caches of its own is closed, and the default branch's next run ends
- **THEN** the repository holds no cache of that pull request

#### Scenario: A job that fails before its downloads end
- **WHEN** a firmware job fails before every source of its build is downloaded
- **THEN** it saves no download cache

#### Scenario: Room for the jobs that save at once
- **WHEN** the room left in the quota fits one board's compiler cache but not one for every board
- **THEN** no board's job of a branch's run saves its compiler cache

## ADDED Requirements

### Requirement: Workflows cancel only their own superseded runs
A run of a workflow SHALL cancel only the runs of the same workflow on the same ref that a newer commit superseded. A re-run of an older run MUST NOT cancel a newer one, and the weekly audit and a run for a push MUST NOT cancel each other.

#### Scenario: Re-run of an older run
- **WHEN** a job of an older run of the build workflow is re-run while a newer run of the same ref is in progress
- **THEN** the newer run goes on, and the re-run waits for it

#### Scenario: Weekly audit and a push
- **WHEN** a push to the default branch comes while the weekly audit runs
- **THEN** both runs go on

### Requirement: Documents that tests read run the tests
A change to a document that a system test reads SHALL run the build workflow, whose system tests read it; other changes to documentation alone SHALL NOT.

#### Scenario: A document a test reads
- **WHEN** a commit changes only a document that a system test reads
- **THEN** the build workflow runs for it

#### Scenario: A document no test reads
- **WHEN** a commit changes only documentation that no system test reads
- **THEN** the build workflow does not run for it

### Requirement: One pinned Nix in every job
Every job of the workflows SHALL install the same pinned release of the Nix installer, so that what runs with the release keys, and every build, gets the Nix of a known version.

#### Scenario: Installer of every job
- **WHEN** the workflows' jobs are inspected
- **THEN** each installs Nix through the one definition that names the installer's release
