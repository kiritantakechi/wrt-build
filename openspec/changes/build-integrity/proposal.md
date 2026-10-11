# Proposal

## Why

Two faults keep builds from reusing exactly what is still valid:
- **A changed toolchain patch leaves the old toolchain in place.** Patch 0020 added a GCC patch, and `just toolchain-build dev` in an existing tree did not rebuild GCC. OpenWrt names the toolchain components' prepared stamps without their content, and it builds the toolchain anew only in buildbot mode, when the last git commit of `toolchain/` changes (`.ver_check`). Even then it cleans only the configuration at hand: here every board has a build directory of its own, and those keep their packages compiled by the old toolchain. Nothing covers the generic kernel patches either, although the toolchain's kernel headers come from them. build/environment requires that a build rebuild "all that the change affects".
- **A branch's CI run evicts main's caches.** GitHub keeps 10 GB of caches per repository and evicts the least recently used past that. While a branch runs, main's caches are not used, and the branch's own push them out. Main's first run after device-modernization's merge found no compiler cache and built its firmware from 11.7 % hits: 110 and 138 minutes instead of about 40. It happened before too, during board-model.

## What Changes

- **The toolchain is built as a whole when its inputs change** (an openwrt patch generalizing the buildbot-only check to every build):
  - The toolchain records the content of its inputs: the `toolchain/` directory, and the generic kernel files of the target's kernel version, from which its kernel headers come. It is built anew when they change, in any mode, with or without git.
  - Every target build directory records the toolchain it was built with. A board's build directory and staging directory are cleaned when that is no longer the toolchain at hand, whether its inputs, its GCC version or its C library changed.
  - The buildbot-only checks that this replaces go: the git-based `.ver_check` and `check-toolchain-clean.sh` with its manual `toolchain/build_version` knob. The knob's file stays an input, so a bump still rebuilds.
  - `toolchain-build.sh` no longer writes `.ver_check` from git.
- **The CI toolchain key covers the generic kernel files** too, so that the host stage builds again whenever the toolchain's own check would.
- **Main's caches stay whole** (`build.yml`):
  - A run on another branch saves a compiler or download cache only when the repository's caches, with it, stay within the quota. Otherwise it goes on with the caches it restored, main's among them.
  - It always saves the toolchain, which its firmware jobs need.
  - Main's runs delete the caches of branches merged into main, or deleted.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `build/environment`: a change to the toolchain's files rebuilds the toolchain and every board's packages with it.
- `build/ci`: the toolchain key covers the generic kernel files; branch runs keep main's caches whole, and a merged branch's caches go.

## Impact

- `patches/openwrt/`: a new patch to `toolchain/Makefile`, the top-level `Makefile` and `scripts/check-toolchain-clean.sh`.
- `scripts/toolchain-build.sh`, `scripts/toolchain-key.sh`, a new CI cache script with its `just` recipe, `.github/workflows/build.yml`, `docs/ci.md`, `docs/dev-setup.md`, `docs/patches.md`.
- The first build of each tree after the patch builds the toolchain and every board anew, once: no tree has the new records yet. CI's toolchain key moves once, as `toolchain-key.sh` changes.
- A toolchain change now costs a full target rebuild locally, as it does in CI, where a new compiler misses every compiler cache entry.
- A branch run with little room in the quota saves no compiler cache. Its next run then restores main's, which serves every source the branch left as main has it.
- Order: after device-robustness.
