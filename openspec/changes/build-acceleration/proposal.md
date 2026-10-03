# Proposal

## Why

A firmware job takes 3.5 to 4.7 hours whether its compiler cache is warm or cold, and a local `just build` takes 26 minutes when nothing changed. Neither is spent on what changed.

What run 36848242349 and the local VM show:
- **Rust is rebuilt in every firmware job.** Each firmware job, and each board's first local build, compiles the Rust host toolchain from source, LLVM included. Rust took 157 minutes of the R4S build (AMD EPYC 9V74) and 211 of the R6S build (AMD EPYC 7763). For the last 47 and 66 minutes nothing else was left to build.
- **Go is rebuilt too.** The Go host toolchain adds about 20 minutes per job.
- **The compiler cache cannot help.** ccache covers only C and C++. So a warm build takes as long as a cold one.
- **A cached host build would not be reused.** OpenWrt names a package's prepared stamp after the modification times of its files. A host build packed in one job therefore never matches the stamps of another job's fresh checkout.
- **A local build re-applies every patch.** `just build` resets the tree and applies the whole series again, which gives every patched file a new modification time. The kernel is then extracted and compiled again: about 3,500 compiles, 99.8% of them ccache hits, still 26 minutes.
- **Only C and C++ keep a cache between CI runs.** Go's build cache sits in the tree's `tmp/`, and Rust packages have none.
- **A changed compiler flag rebuilds nothing.**
  - A package's configured stamp names only the package's own configuration symbols, not the target's compiler flags.
  - `toolchain-build` rebuilds a toolchain only when its C library changed.
  - So in an existing tree, `toolchain-o3`'s `-O3` would leave every package and the toolchain at `-O2`.

The change has to come before `toolchain-o3`, whose first run rebuilds everything cold, and whose flags have to rebuild a local tree. At `-O2` the R6S firmware job already took 284 of its 330 minutes.

## What Changes

Four rules, applied the same way to CI and local builds, to every board and to every language.

- **Measure every build.** `build.sh` and `toolchain-build.sh` record OpenWrt's build time log (`BUILD_TIME_LOG`). At the end of each build they print the stages with the most wall share and solo time, so every gain below is measured, not guessed.
- **Build each toolchain once.** The host stage builds every toolchain the firmware needs, from the board-neutral configuration, and the toolchain archive carries them all:
  - the host tools and the cross toolchain, as today;
  - the Go host toolchain;
  - the Rust host toolchain. A patch to the packages feed installs Rust under `staging_dir/hostpkg`, as Go already is, instead of once per board. It builds LLVM only for the host and the target, and sends LLVM's C++ through ccache.

  Firmware jobs compile target code only. A board's build fails if it compiled a toolchain, or changed one. The cache key already covers the feed's Go and Rust directories, and now they matter.
- **Rebuild only what changed, and everything that did.** A step's stamp names everything it was built from.
  - A patch to OpenWrt names prepared stamps after the content of their files, so an unpacked host build is up to date in any checkout of the same sources.
  - The same patch names prepared stamps after the target's compiler flags as well, so a changed flag prepares, and so rebuilds, every package. The kernel needs nothing: OpenWrt runs Kbuild on every build, and Kbuild compares each object's command line.
  - `toolchain-build` rebuilds the toolchains whose recorded flags differ from the configuration's.
  - The patch step applies the series as commits in the object database. It then moves the work tree from the previous patched commit to the new one, so git rewrites only the files whose content changes. A series that does not apply leaves the tree untouched.
  - `fetch` no longer resets an existing tree.
- **Keep a compiler cache for every language**: ccache for C and C++, Go's build cache, and sccache for Rust packages. They live together in `$WRT_WORKDIR/compiler-cache`, beside the tree, so they outlive it.
  - In CI, each stage keeps one compiler cache per run: one for the host stage, and one for each board. Each is trimmed to what its build used.
  - The `caches` job keeps the newest of each.

Expected results, to be confirmed by the time reports:

| Build | Today | Expected |
|---|---|---|
| Firmware job, host stage and compiler cache warm | 3.5–4.7 h | under 1 h |
| Firmware job, compiler cache cold | 3.5–4.7 h | 1.5–2.5 h |
| Host stage after its key changed | 80 min | 2.5–3.5 h cold, 1–1.5 h from its compiler cache |
| Local `just build` with nothing changed | 26 min | a few minutes |
| Local first build of a second board | Rust again, LLVM included | no toolchain work |

### Non-goals

- **Test time.** The system tests run under TCG; they are a change of their own.
- **Prebuilt Rust.** Taking Rust from rust-lang's binaries would be faster still, but it is not the compiler the packages feed builds and tests. The feed's recipe stays, built once.
- **Optimization levels.** These belong to `toolchain-o3`.
- **Larger or paid runners.**

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `build/ci`:
  - the host stage builds the host tools, the cross toolchain, and the Go and Rust host toolchains; firmware jobs compile none of them;
  - every stage keeps a compiler cache for each language it compiles, and rebuilding unchanged sources is served from them.
- `build/environment`:
  - the working directory holds the compiler caches of every language;
  - entry points rebuild only what changed, and all that a changed compiler flag affects (new requirement);
  - every build reports where its time went (new requirement).
- `build/boards`: "One toolchain for every board" covers the Go and Rust toolchains as well as the cross toolchain, and the toolchain is built anew when the configuration's flags differ from those recorded.

## Impact

- **Scripts**:
  - `scripts/lib.sh`:
    - the series applied as commits, and the move of the work tree;
    - `link_tree` links the compiler cache directories;
    - the tree's links, files and configuration keep their times when unchanged;
    - helpers for the time log, the cache trim and the toolchain guards;
  - `scripts/fetch.sh` and `scripts/patch.sh`;
  - `scripts/toolchain-build.sh`: the Go and Rust host toolchains, the time log, and the toolchains' record with its flags;
  - `scripts/toolchain-key.sh`: the build files that name the stamps the archive carries;
  - `scripts/toolchain-pack.sh` and `scripts/toolchain-unpack.sh`: `staging_dir/hostpkg` and the stamps of `build_dir/hostpkg`;
  - `scripts/build.sh`: the time report, the toolchain guards, the statistics and trimming of every compiler cache.
- **Patches**, each with an `Upstream-Status` trailer from the start:
  - `patches/openwrt/0011`: prepared stamps named after content and the target's compiler flags (`Pending`);
  - `patches/packages/0002`: Rust under `staging_dir/hostpkg`, LLVM for the host and the target only, through ccache (`Inappropriate`: every board here shares one architecture).
- **Configuration**:
  - `config/toolchain.seed`: sccache for Rust packages;
  - `flake.nix`: sccache in the build environment, which changes `WRT_BUILD_INPUTS` and so the toolchain key.
- **CI**, in `.github/workflows/build.yml`:
  - the host stage restores the download cache and its own compiler cache;
  - the compiler cache keys become `compiler-cache-<stage>-…`;
  - the `caches` job keeps one per stage.
- **Tests**:
  - `tests/build/test_environment.py`: re-applying a series;
  - `tests/build/test_boards.py`: the toolchain guards;
  - `tests/unit/test_lib.py`: the cache trim, the toolchain guards' helpers, and the writes that keep times;
  - `tests/verified-elsewhere.toml`: the scenarios CI and the build prove.
- **Docs**: `docs/ci.md` (stages, caches, budget and timings) and `docs/dev-setup.md` (the compiler cache directory).
- **Disk**:
  - locally, one Rust build instead of one per board: each board's Rust build directory takes about 21 GB of the work volume;
  - in CI, the toolchain archive grows by the Go and Rust toolchains, and a host compiler cache joins the board caches. `docs/ci.md` keeps the budget against the 10 GB quota.
- **Order**: the first of three changes, after the archived `board-model`: `build-acceleration`, then `toolchain-o3`, then `device-modernization`.
