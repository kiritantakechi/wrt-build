# Proposal

## Why

The audit of 2026-10-26 also read the pipeline that builds, signs and publishes releases, and the host-side scripts it runs. Each finding below was checked against the workflows and scripts:

- **Publish:** a re-run of an older main run publishes its build as the newest stable release, which routers then download. The re-run also cancels the newer run that is in progress. A release's tag lands on whatever the default branch holds at publish time, not on the commit that was built. The notes take their upstream commits from the checkout, not from the builds, and the manifest records no commit of this repository.
- **Signing:** the signing job names each build's output directory after the unverified `board` field of its manifest, and copies whatever the artifact holds, listed or not. The key-holding job also installs whichever Nix release is newest that day. A malformed checksum line passes every check unless `--strict` is given.
- **Merge gate:** a pull request's run reports the required `upgrade-drill` check as passed without drilling. A bump branch can therefore merge on it.
- **Bump:** when opening the pull request fails, as it does today, the branch's check and build are never started. A second run on the same day fails on its own branch.
- **Caches:**
  - A job that fails before its downloads saves an empty download cache under the exact key, which later jobs cannot replace.
  - Pull-request caches are never pruned.
  - Hyphenated board ids would break the per-stage pruning.
  - Parallel jobs each count the quota's room as if they were alone.
  - The toolchain key misses a change of the target's kernel version.
- **Workflow triggers:** documentation that system tests read never triggers them. The weekly audit and a push to main cancel each other.
- **Build output:** a board's output directory keeps the packages of every package an earlier build packed, also once the configuration no longer builds it. After a kernel update, the package index and the release carried an older kernel's kmods beside the new ones, which a router could install and not load.
- **Warnings' records:** the build records a package's UB-indicative warnings from its compile log whenever that log holds more than make's time line. OpenWrt rewrites the log also when it only packs the package again, as when its apk is gone from the output directory or its packaging rules change, and that log holds the packing's lines alone: the package's warnings were forgotten, and the register check would miss them or call their reviews stale.
- **Host scripts:**
  - `just` pastes its arguments into the command line;
  - the patch series' commits depend on the user's git configuration;
  - the UBSan check passes when its `nm` cannot run;
  - `marks-check` passes on a directory it cannot read;
  - `toolchain-pack` and `toolchain-unpack` resolve a relative archive path differently.

## What Changes

- **Publish** only from the commit its branch still holds, and tag the release on that commit. Fail when the checkout's `upstream.lock` is not the builds' own. Record this repository's commit in the manifest and require it to be the same for every board. A re-run waits for the runs in progress and never cancels them.
- **Signing:** each build is taken by its artifact's name and checked against its manifest, which lists every file of the build, the packages included. Only the files the manifest lists are signed and passed on, and they must be plain relative paths. Every checksum check is `--strict`. The Nix installer is pinned, in one local action that every job uses.
- **The required check** fails on a pull request's run of a bump branch: only the branch's own run, which drills, passes it.
- **Bump:** starts the branch's check and build before it opens the pull request, never overwrites an existing branch, and opens the pull request a rerun still lacks. `github-audit` reads back whether workflows may open pull requests.
- **Caches:**
  - a download cache is saved only once every download finished;
  - main prunes the caches of closed pull requests;
  - families of compiler caches are named by their whole stage;
  - the room counts every board's job saving at once;
  - the toolchain key covers the target's kernel version.
- **Triggers:** the documents that tests read run the build workflow; the weekly audit has a concurrency group of its own.
- **Build output:** before make, the build removes the packages the configuration does not build from the board's output directory.
- **Warnings' records:** a package's record changes only when the build compiled it, as the build's time log says; the time log names a host build's stages apart from the target build's (patch 0042).
- **Host scripts:**
  - `just` passes arguments as given;
  - the series commit ignores the user's and the system's git configuration;
  - the UBSan check fails when `nm` cannot run;
  - `marks-check` fails on a path it cannot read;
  - the archive path is resolved the same way when packing and unpacking.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `release/publishing`: publish from the branch's current commit only, tagged on it; notes from the builds' lock; boards from one commit of this repository.
- `release/signing`: builds taken by their artifact's name, only listed and plain paths signed, strict checksums.
- `release/upstream-bump`: the bump starts its checks before the pull request and never overwrites its branch; a pull request's run never passes the drill check of a bump.
- `build/ci`: caches saved whole and pruned for closed pull requests; the toolchain key covers the kernel version; the documents tests read trigger them; workflows cancel only their own superseded runs; the installer is pinned.
- `build/upstream-pinning`: the same lock yields the same commits whatever the git configuration.
- `build/environment`: entry points pass their arguments as given.

- `quality/undefined-behavior`: the warnings of a package the build packs again without compiling it still count.

`build/ci`'s "Complete manifest" and `release/publishing`'s "Inspect Release contents" do not change: an incremental build now does what they already say.

## Impact

- `.github/workflows/build.yml`, `check.yml`, `bump.yml`; a new `.github/actions/nix/action.yml`.
- `scripts/release-publish.sh`, `release-sign.sh`, `build.sh`, `drill-base.sh`, `cache-prune.sh`, `cache-room.sh`, `toolchain-key.sh`, `toolchain-pack.sh`, `github-audit.sh`, `marks-check.sh`, `lib/upstream.sh`, `lib/tree.sh`; new: `scripts/download.sh` and `scripts/lib/manifest.sh`; the `justfile`.
- Tests in `tests/build`, `tests/release`, `tests/unit`, the patch series' scratch repository moved to `wrt_tests/model/series.py`; `docs/ci.md`, `docs/release-flow.md`, `docs/dev-setup.md`.
