# Design

## Context

See proposal.md for why. The current state:

**How OpenWrt decides to rebuild its toolchain.**
- The toolchain components override the content-named prepared stamps of host builds with fixed names (`include/toolchain-build.mk`, `toolchain/gcc/common.mk`), and turn auto-rebuild off. A component is built again only once its build directory is gone.
- In buildbot mode only, two checks clean up:
  - `toolchain/Makefile`'s `.ver_check` names the last git commit of `toolchain/`. When that changes, it removes `BUILD_DIR`, `STAGING_DIR`, `TOOLCHAIN_DIR` and `BUILD_DIR_TOOLCHAIN`, the configuration at hand's. It needs `.git`.
  - `scripts/check-toolchain-clean.sh` compares `CONFIG_GCC_VERSION` and `toolchain/build_version` with a record in the tree, and runs `make targetclean`.
- The three GCC passes share one patched source tree. Rebuilding one pass and not the others would leave a toolchain partly old: final's binaries overwritten by initial's install, and the C library compiled by the old compiler. Upstream treats the toolchain as one unit for this reason.
- The toolchain's kernel headers come from the kernel tarball with the generic kernel patches (`target/linux/generic/{backport,pending,hack}-<version>`, the generic files). `make world` enters `toolchain/compile` only when a file under `toolchain/` is newer than its compile stamp.
- `$(target/stamp-compile)` depends on `$(toolchain/stamp-compile)` and on `$(BUILD_DIR)/.prepared`.

**How this project builds.**
- One board-neutral toolchain serves both boards (`just toolchain-build`). Each board then builds in directories of its own (`build_dir/target-*_<board>`, `staging_dir/target-*_<board>`).
- `toolchain-build.sh`:
  - rebuilds the toolchain when the configuration's flags or its C library differ from its record, `wrt-toolchain.json`;
  - writes `.ver_check` from `git log -1 toolchain`, so that the ci profile, which sets `CONFIG_BUILDBOT=y`, keeps a toolchain the host stage packed.
- CI's toolchain key (`scripts/toolchain-key.sh`) hashes the `tools/` and `toolchain/` trees and the build files that name host stamps, but not `target/linux/generic`.

**CI caches** (`build.yml`):
- The host stage saves the toolchain archive (`toolchain-<key>`, about 1.1 GB, exact key) and its compiler cache. Each firmware job saves a download cache (`dl-<hash>`, about 2.4 GB) and its board's compiler cache (`compiler-cache-<board>-<settings>-<run>`, about 2 GB).
- The `caches` job (`actions: write`, no checkout) keeps, on the run's own ref, the current toolchain and the newest download and compiler caches, and deletes the rest.
- GitHub lets a branch restore the default branch's caches, but not the reverse. Past 10 GB it evicts the least recently used caches, of any ref, within hours. A full set of main's is about 7.6 GB.

## Goals / Non-Goals

**Goals:**
- One mechanism for "the toolchain changed", in OpenWrt, for every mode and every configuration directory.
- CI's key moves whenever that mechanism would rebuild, so that the firmware stage never meets a toolchain its tree would rebuild.
- The default branch's caches survive any branch's runs.

**Non-Goals:**
- Rebuilding a single toolchain component. The toolchain stays one unit, as upstream builds it.
- Toolchain configuration options other than the toolchain's identity: the GCC version, the C library and the architecture name the toolchain directory, and this project's record covers the flags. Options such as extra GCC configure arguments keep their present (missing) handling.
- Choosing which caches GitHub evicts. The policy keeps the repository within the quota instead.

## Decisions

### D1. The toolchain records its inputs' content

- `toolchain/Makefile`'s `.ver_check` stays the toolchain's record, at the same path and for every build. Its content is the content hash (`find_md5_reproducible`) of the `toolchain/` directory and of the generic kernel files of the target's kernel version: its version file, the backport, pending and hack patch directories, and the generic files directories.
- When the hash differs from the record, or there is none, the rule removes `TOOLCHAIN_DIR` and `BUILD_DIR_TOOLCHAIN` and writes the new hash. The prerequisites of the toolchain's prepared state, `info.mk` and `STAGING_DIR/.prepared`, depend on it, as they do in buildbot mode today.
- `toolchain/compile` is entered when a file of those generic kernel directories changes, as it is for `toolchain/` today: they join the inputs of the toolchain's compile stamp.
- The hash covers content, not modification times or commits. A checkout of the same sources, an uncommitted edit, and a tree without `.git` all behave the same.
- `toolchain/build_version` is a file of `toolchain/`, so bumping it still rebuilds. `check-toolchain-clean.sh` and the top-level `toolchain_rebuild_check` go, with their record of the GCC version, which D2 covers.

Alternatives considered:
- **Content-named prepared stamps per component:** they rebuild one component, or the three GCC passes in some order. That gives the partly old toolchain described above, and the C library would keep objects of the old compiler.
- **Keeping git:** it needs `.git` and a commit, and misses an edit made before committing.

### D2. A target build directory records the toolchain it was built with

- `$(BUILD_DIR)/.toolchain` names the toolchain directory and the content of its `.ver_check`.
- A rule that runs after the toolchain is up to date compares it with the toolchain at hand. When they differ, it removes `BUILD_DIR` and `STAGING_DIR` of the configuration at hand, and records the new one. `$(BUILD_DIR)/.prepared` depends on it, so every target stamp comes after.
- The record names the toolchain directory, whose name holds the GCC version, the C library and the architecture. So a change of any of them, which builds a toolchain in another directory, also cleans the target.
- Each board's directories carry their own record. A toolchain rebuilt for one board's build, or by `just toolchain-build`, cleans each board when that board builds next, and only then.

This splits buildbot's single cleanup into its two halves. Each half cleans what it owns, and each configuration directory decides for itself.

### D3. toolchain-build.sh stops writing `.ver_check`

- `make toolchain/install` builds the record through D1's rule, so the `git log` line and its comment go.
- The record of the flags (`wrt-toolchain.json`) stays: D1 covers the toolchain's files, and the record its flags.
- The compile stamp the script builds after the install still keeps `make world` out of `toolchain/compile` on a restored toolchain.

### D4. CI's toolchain key covers the generic kernel files

`toolchain-key.sh` adds the tree of `target/linux/generic`:
- It is a superset of D1's generic inputs: other kernel versions' directories and the generic kernel configuration count too. A change there costs a host stage that D1 alone would not need, which is rare and safe.
- A key that moved less often than D1's record would hand the firmware stage a toolchain whose record its tree contradicts. D1 would then remove it, and the stage would fail on compiling toolchain parts.

### D5. Branch runs save within the quota's room

A new script, `scripts/cache-room.sh <path>...`, run in the build jobs before each save of a compiler or download cache:
- It prints `save=true|false` for the step's output.
- On the default branch: always true. Main's caches are the ones to keep current, and the `caches` job prunes main's superseded ones after the run.
- On another ref: true only when the repository's present cache usage (`GET /repos/{repo}/actions/cache/usage`) plus the size of the paths stays within `CACHE_QUOTA` (10 GB, the repository's limit). Everything present counts, the ref's own older caches too: they still exist until the `caches` job runs, and GitHub could evict main's in between.
- The toolchain archive is saved as before, without the check: the firmware jobs restore it with `fail-on-cache-miss`.
- The build jobs get `actions: read` for the usage call, and nothing more.

A branch whose first run filled the room still restores its own caches, or main's, on later runs. Their restore keeps main's caches recently used.

### D6. Main's runs delete merged and deleted branches' caches

The `caches` job, on the default branch only, deletes the caches of every `refs/heads/<branch>` that either:
- no longer exists, or
- GitHub's compare API reports as `behind` or `identical` to the default branch, that is merged.

The pruning of superseded caches moves from inline `awk` into a script, `scripts/cache-prune.sh`, next to the merged-branch cleanup, so that both are tested with a stand-in `gh`. The job checks out the repository for it. It still runs no build code, and has `actions: write` alone.

### D7. Tests and verification

- **D1 to D3** on the VM (dev profile):
  - Adding a no-op GCC patch rebuilds the toolchain. The board built next compiles every package anew, and so does the other board.
  - Removing the patch does the same again.
  - A rebuild with nothing changed rebuilds nothing.
- **D4 and D5 in CI:**
  - This change's branch runs with main's caches present. Main's caches are all still there after the runs, as `gh cache list` shows, and the branch saved only what fit.
  - Main's run after the merge deletes the branch's caches.
  - The runs and listings go to `docs/ci.md` and `tests/verified-elsewhere.toml`.
- **Unit tests** of both scripts with a stand-in `gh`, in the tests' unit suite:
  - the room check on the default branch and on another ref, with and without room;
  - the pruning of superseded caches;
  - the merged, deleted and unmerged branches.

## Risks / Trade-offs

- [Every tree builds everything once after the patch] → The records do not exist yet. One full build per board locally; CI builds anew under the moved key anyway.
- [A toolchain change costs a full target rebuild locally] → That is what correctness costs: CI pays it already, as a new compiler misses every compiler cache entry. ccache's content-based compiler check keeps the old toolchain's entries for a change that is undone.
- [A branch that changes the toolchain gets no room for its compiler caches] → Its runs compile from what main's caches serve, which is little for a new compiler. That is the price of keeping main whole; such branches are rare, and their merge makes main build anew anyway.
- [GitHub's usage figure lags a save by a little] → The check runs before each save, and the quota leaves the toolchain's 1.1 GB of headroom: a full set of main's is about 7.6 GB.
- [The generic kernel files change with every kernel bump] → A kernel bump rebuilds the toolchain locally and in CI. That is correct: its kernel headers change with it.

## Migration Plan

- The first build after `just patch` rebuilds the toolchain and each board. Nothing to do by hand.
- The first branch run under D5 may find the repository already past the quota (12.4 GB on 2026-10-11). It then saves no compiler cache, and GitHub's eviction or main's next `caches` job brings the total down.
- Rollback: reverting the patch and the workflow restores today's behavior. The records left behind are ignored.
