# Proposal

## Why

Target packages build at `-O2` on top of OpenWrt's `-Os`. The project wants aggressive optimization, and the choice made with the board model is `-O3` without fast-math, so that floating-point code keeps IEEE semantics. `-O3` inlines, clones, unrolls and vectorizes far more than `-O2`. Undefined behavior that happened to work at `-O2` is then more likely to turn into wrong code, and the new diagnostics break packages that build with `-Werror`. The switch therefore needs a systematic way to find the undefined behavior it exposes and to fix it upstream-style, not a hope that the tests notice.

The switch also rebuilds every package. That makes it the moment to audit every carried patch against the current pins:
- patch 0002 edits a boot script that the A/B images no longer run;
- the BBRv3 series comes from a third-party build script rather than from its primary source;
- nothing records, for each patch, what it is for and whether upstream has it.

## What Changes

- **`-O3` for target userspace**:
  - C and C++ packages, and GCC's runtime libraries (libgcc, libstdc++), compile with `-O3` and the board's `-mcpu`, after the default `-Os`.
  - The kernel and its modules stay at `-O2`, the level upstream Linux supports. `CONFIG_KERNEL_CFLAGS` follows the shared optimization flags in the kernel's `KCFLAGS`, so it wins there.
  - musl keeps its own level, as OpenWrt filters `-O` flags out of its build.
  - BPF objects keep clang's `-O2`. Rust and Go are unaffected.
  - The board-neutral toolchain is rebuilt under a new cache key. In an existing tree, `build-acceleration`'s stamps rebuild the toolchains and every package with the new flags by themselves, so no clean is needed.
- **Never fast-math**: no `-Ofast`, `-ffast-math` or other relaxed floating-point flag reaches a compile.
- **Build failures under `-O3` are fixed in the source**, by patches. A package-level opt-out stays a registered last resort, as LTO's is.
- **Undefined behavior, found in two ways**:
  - **Warnings**: the build collects the warnings of a fixed set of UB-indicative GCC options (out-of-bounds, overflow, uninitialized, use-after-free, aliasing, alignment) from the packages the image ships. The collection goes into the build outputs. A test fails on any warning that is neither fixed by a patch nor reviewed, with a reason, in `tests/reviewed-warnings.toml`, data like `tests/verified-elsewhere.toml`.
  - **A `ubsan` profile**: the dev profile with UBSan in trap mode, which needs no runtime, for every target package. The toolchain's libraries and the kernel stay uninstrumented, and the profile builds in directories of its own. The system tests run on it locally. A trap fails the test it happened in, naming the process. A small probe package proves that the detection works.
  - Every undefined behavior found is fixed by a patch.
- **Patch audit, every patch stating its upstream status**:
  - Every carried patch is reviewed against the current pins: OpenWrt, packages, QEMU and the feed packages' own patches.
  - A patch is dropped when it is dead or upstream has it. 0002 goes: the A/B boot environment already passes the f2fs compression option. A patch's number is its identity: a dropped patch leaves its number unused, and no patch is renumbered.
  - BBRv3 is re-derived from its primary source, the google/bbr v3 branch as rebased for 6.18.
  - Each remaining patch gets a correct, current message.
  - Each patch states its upstream status in an `Upstream-Status` trailer, in OpenEmbedded's vocabulary: `Pending`, `Submitted [where]`, `Backport [source]` or `Inappropriate [reason]`. The status lives in the patch itself, so no separate list can drift from the files.
  - `docs/patches.md`, which replaces `docs/upstream-contributions.md`, describes the convention and keeps the write-ups of the patches meant for upstream. A test reads every patch's trailer, and holds the write-ups and the `Pending` and `Submitted` patches in step.
- **Size recorded**: the image grows. The growth is measured per board and recorded against the 1 GiB root partition.

## Capabilities

### New Capabilities
- `quality/undefined-behavior`: UB-indicative warnings in shipped packages are fixed or reviewed; under the `ubsan` profile a trap fails the test it happens in.

### Modified Capabilities
- `firmware/toolchain`:
  - target userspace optimizes with `-O3` instead of `-O2`;
  - the kernel keeps `-O2` (new requirement);
  - no relaxed floating-point semantics (new requirement).
- `build/upstream-pinning`: every patch states its upstream status in its own trailer (new requirement).

## Impact

- **Configuration**:
  - `config/toolchain.seed`: the optimization flags and the kernel's `-O2`;
  - `config/profiles` and `config/ubsan.seed`: the `ubsan` profile, whose seeds after a `|` apply to the boards only.
- **Scripts**:
  - `scripts/lib.sh` (`compose_seeds`);
  - `scripts/config.sh`: the build suffix of the `ubsan` profile;
  - `scripts/build.sh`: the warnings collection, and the kernel's flags in the manifest.
- **Patches**: `patches/openwrt/` (0002 dropped, BBRv3 re-derived, fixes for undefined behavior), the feed packages' own patches, and a probe package in the feed.
- **Tests**:
  - `tests/firmware/test_toolchain.py`: `-O3`, the kernel's flags and fast-math;
  - new `tests/quality/test_undefined_behavior.py`;
  - the trap check in the router fixture;
  - new `tests/build/test_upstream_pinning.py`, over every patch's trailer, and `tests/unit/test_patches.py`;
  - `tests/reviewed-warnings.toml`, the reviewed warnings;
  - `NEUTRAL_CFLAGS` in `tests/build/test_boards.py`.
- **Docs**:
  - `docs/patches.md` replaces `docs/upstream-contributions.md`;
  - `docs/undefined-behavior.md`: how warnings are reviewed, and how and when the `ubsan` profile runs;
  - `docs/lto-optouts.md` becomes `docs/optimization.md`: the flags, the LTO and `-O3` opt-outs, and the image sizes.
- **CI**: the toolchain key changes. On `build-acceleration`'s pipeline, the first run builds the host stage anew, its compiler cache serving what the flags do not touch (tools, the compilers, LLVM), and every firmware job compiles its packages cold; later runs hit again. The `ubsan` profile is not run in CI: it doubles a build, and CI has no time to spare.
- **Disk**: the `ubsan` profile adds one board's build directories, about 45 GB, for as long as it is kept.
- **Order**: the second of four changes, after the archived `board-model`: `build-acceleration`, then `toolchain-o3`, then `module-boundaries`, then `device-modernization`.
