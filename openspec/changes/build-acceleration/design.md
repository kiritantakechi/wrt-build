# Design

## Context

See proposal.md for why. The facts the approach rests on:

**Where a build's time goes.** The figures come from the firmware jobs of run 36848242349 (from GitHub's timestamps of the make steps) and from the local VM's last no-change build.

| Stage | R4S, AMD EPYC 9V74 | R6S, AMD EPYC 7763 |
|---|---|---|
| Kernel (`target/compile`) | 41 min | 57 min |
| Go host toolchain (`golang-bootstrap`, `golang1.27`, `golang`) | about 16 min | about 20 min |
| Rust host toolchain (`rust/host`, LLVM included) | 157 min | 211 min |
| of which with nothing else left to build | 47 min | 66 min |
| Rust packages after it (einat, netavark, aardvark-dns), podman | 6 min | 8 min |
| Whole build | 207 min | 280 min |

Locally, the no-change build re-extracted the R6S kernel, compiled `vmlinux` again in 7 minutes with ccache hits, then the packages that build against the kernel, then the image: 26 minutes in all.

**How OpenWrt decides that a step is done.**
- A package's prepared stamp is named after a hash of its directory's files (`PKG_FILES_MD5`, `include/depends.mk`), and the kernel's after its patches and files (`include/kernel-build.mk`).
- Without `CONFIG_AUTOREMOVE`, which neither profile sets, that hash covers each file's path and modification time (`find_md5`). Only with it does the hash cover content (`find_md5_reproducible`).
- Separately, `rdep` rebuilds a step when any of its files is newer than its stamp.
- A package's configured stamp is named after the values of the package's own configuration symbols (`PKG_CONFIG_DEPENDS`, `include/package.mk`). The target's compiler flags (`CONFIG_TARGET_OPTIMIZATION`, `CONFIG_EXTRA_OPTIMIZATION`) are in none of them, so changing a flag rebuilds no package.
- The kernel is different: OpenWrt runs Kbuild on every build (its `.modules` and `.image` targets depend on `FORCE`), and Kbuild recompiles every object whose command line changed.
- `toolchain-build.sh` builds the toolchain anew only when its C library is not the one its record names, never because the recorded flags differ.
- Tools and the cross toolchain are also guarded by top-level stamps under `staging_dir`, which `toolchain-unpack` touches. So make never descends into them, and a firmware job keeps the restored ones. Host packages such as Go and Rust have no such stamp: make checks each one's own stamps, and a fresh checkout changes their names.

**Where the host toolchains live.**
- Host packages build in `build_dir/hostpkg` and install into `staging_dir/hostpkg`, shared by every board's build. Go does this.
- The feed's Rust recipe instead builds in the board's build directory and installs into the board's target staging directory (`$(STAGING_DIR)/host`). Each board therefore builds its own Rust, although all boards compile for the same target (`aarch64-unknown-linux-musl`). Locally the R6S's Rust build directory is 21 GB.
- Rust's installed stamp is already in `staging_dir/hostpkg`, and package builds already find `staging_dir/hostpkg/bin` on their `PATH` (`TARGET_PATH_PKG`).
- The recipe builds LLVM from source, for all of its about 14 backends.

**The patch step.** `fetch` and `patch` each reset every repository to its pinned commit, and `patch` then applies the series with `git am`. Every file a patch touches is written twice, and gets a new modification time, on every run.

**Compiler caches.**
- **C and C++**: ccache lives in `$WRT_WORKDIR/ccache`, linked as the tree's `.ccache`. In CI there is one per board, trimmed to what the build used (`WRT_CCACHE_TRIM`).
- **Go**: Go's build cache is the tree's `tmp/go-build`, 5.3 GB locally, and is lost with each CI runner.
- **Rust**: Rust packages have no cache. The feed offers sccache (`CONFIG_RUST_SCCACHE`, cache directory `$(TOPDIR)/.sccache` by default), which the build environment does not have.

**Build time log.** OpenWrt records a begin and an end event for every prepare, configure, compile and install stage when `BUILD_TIME_LOG` names a file. `scripts/build-time-report.pl` turns that log into a report:
- **wall share**: each second divided among the stages that run in it;
- **solo time**: the seconds in which a stage runs alone, the part of the build that only a faster stage would shorten.

**Cache budget.** Main's caches after run 36848242349 took 6.2 GB of the 10 GB quota: toolchain 775 MB, downloads 2,685 MB, and a compiler cache of about 1,360 MB per board.

## Goals / Non-Goals

**Goals:**
- **Toolchains**: every toolchain is built once per change of its inputs, and firmware jobs compile target code only.
- **Rebuilds**: whether a step is done is decided by content, the same way locally and in CI.
- **Caches**: every language's compilations are cached, in every stage.
- **Evidence**: every claim is measured with the time report.

**Non-Goals:**
- **`CONFIG_AUTOREMOVE`**: it would make stamps content-named, but it deletes every package's build directory after install. That includes the kernel's and U-Boot's, whose configurations `build.sh` copies afterwards, and every directory a local incremental build reuses.
- **Several host jobs or archives** (one per toolchain, with layered keys): see D2.
- **An external LLVM for Rust**: see D3.
- **`-j` tuning and other runner types.**

## Decisions

### D1. Measure with OpenWrt's build time log

- **Recording**: `toolchain-build.sh` and `build.sh` export `BUILD_TIME_LOG=$TREE/logs/build-time-<build>.tsv`, emptied at the start of the build. The build is `host`, or the build directories' suffix (`CONFIG_BUILD_SUFFIX`): the board, or a board and a profile with directories of its own, such as `toolchain-o3`'s `r4s_ubsan`. Each build keeps its own record, as it keeps its own directories.
- **Report**: after make, they print `scripts/build-time-report.pl -n 15` of it.
- **Where it shows**:
  - CI shows the report in the job log.
  - The record sits with the build logs, which CI uploads when a build fails.
  - `docs/ci.md` takes its timings from the reports.

Upstream's own instrument already records every stage of every package, with ends as well as starts. The alternative used for this exploration was GitHub's per-line timestamps on make's progress lines. Those carry only starts, and a step's end has to be inferred from the next line.

### D2. The host stage builds every toolchain

- **Building them.** After the host tools and the cross toolchain, `toolchain-build.sh` builds the Go and Rust host toolchains from the same board-neutral configuration (`package/.../golang/host/compile`, `package/.../rust/host/compile`).
- **Rust becomes board-neutral.** A patch to the packages feed (`patches/packages/0002`) makes the Rust recipe build in `build_dir/hostpkg` and install into `staging_dir/hostpkg`, like every other host package. This is correct for three reasons:
  - every board compiles for the same Rust target;
  - the standard library's C parts compile with the host stage's board-neutral flags, as the C library does;
  - package builds find `cargo` and `rustc` on their `PATH` either way.

  The patch is project-specific: upstream builds one tree for targets of several architectures, whose host toolchains cannot share a directory. It says so in its trailer, `Upstream-Status: Inappropriate [every board of this tree shares one architecture]`.
- **The archive** gains `staging_dir/hostpkg` and the stamps of `build_dir/hostpkg`: the empty dot files `.prepared*`, `.configured` and `.built*`. Rust's 21 GB build tree stays out. `toolchain-unpack` touches the stamps with the rest.
- **The key.** It already hashes the feed's `lang/golang` and `lang/rust` as patched, because `toolchain-key` runs after `patch`. It now hashes what the archive really holds, and the build files that name the stamps of `build_dir/hostpkg` it carries: `include/depends.mk`, `include/host-build.mk` and `rules.mk`. Without them, a change to how a prepared stamp is named would leave the restored stamps stale, and every firmware job would compile Rust for hours before its guard fails. The changed recipe scripts make the first run a cold one.

Alternatives considered:
- **Rust cached per board in the firmware jobs**: still one Rust build per board, two caches instead of one, and the same stamp problem (D4).
- **rust-lang's prebuilt toolchain through Nix**: the fastest, but a different compiler from the one the feed builds and tests, and one whose version follows Nix instead of the feed.
- **One job and archive per toolchain, with layered keys**: a Go or Rust bump would then rebuild only its own toolchain. But it adds jobs and caches against the quota. D3 keeps one cold host stage well inside the job limit, so one stage and one archive are enough.

### D3. A lean Rust build

The same feed patch passes three settings to Rust's bootstrap:
- `--set=llvm.targets=<host>;<target>`, mapping OpenWrt's architecture names to LLVM's (`aarch64` to `AArch64`, `x86_64` and `i386` to `X86`, `arm` to `ARM`, `mips*` to `Mips`, `powerpc*` to `PowerPC`, `riscv64` to `RISCV`, `loongarch64` to `LoongArch`);
- `--set=llvm.experimental-targets=`;
- with `CONFIG_CCACHE`, `--set=build.ccache=$(STAGING_DIR_HOST)/bin/ccache`, which bootstrap uses for LLVM and the other C and C++ it builds.

LLVM is most of Rust's build. rustc needs only the backend of the host, for build scripts and procedural macros, and that of the target. einat's BPF object is compiled by the host's clang (its `build.rs`), not by rustc, so no BPF backend is needed. Through ccache, the host stage's compiler cache serves LLVM whenever only other inputs changed: tools, the cross toolchain, the configuration.

Expected: Rust's build drops from 2.5–3.5 hours, as it ran alongside the packages, to about 1 to 1.5 hours cold, alone. D1 measures it.

The alternative is to link rustc against an external LLVM, the one `flake.nix` already pins for BPF. That builds no LLVM at all, but rustc would then run on an LLVM it is not released with, and the feed's `llvm-tools` dist component needs the in-tree LLVM.

### D4. Stamps named after what built them: content and flags

A patch to OpenWrt (`patches/openwrt/0011`) does two things.

**Prepared stamps after content.** `PKG_FILES_MD5` and the kernel's prepared stamp always hash content, as upstream already does under `CONFIG_AUTOREMOVE`.
- With modification times in the name, a stamp packed in the host job never matches a firmware job's fresh checkout, where every file is new. Go and Rust would then build again despite the restored archive. With content in the name, a stamp names exactly the sources it was built from, in any checkout.
- The `rdep` check still compares modification times. So a local edit, or a `touch` to force a rebuild, still rebuilds.
- The cost is reading files instead of stat-ing them: once per package make, because `PKG_FILES_MD5` is evaluated only once, and about 20 MB of kernel patches per kernel make.

**Prepared stamps after the flags, too.** Every target package's prepared stamp also hashes the symbols `TARGET_CFLAGS` is made of (`CONFIG_TARGET_OPTIMIZATION`, `CONFIG_DEBUG`, `CONFIG_EXTRA_OPTIMIZATION`), which `rules.mk` lists beside it as `TARGET_FLAGS_DEPENDS`.
- A changed flag then prepares every package anew: its build directory is removed and its sources unpacked again, so nothing keeps objects compiled with other flags.
- The configured stamp would not do. A new configured stamp configures and compiles again, but keeps the build directory, and the many packages whose builds do not track their flags (plain makefiles, autotools) then keep their objects. This was found during the implementation; the first plan named the configured stamp.
- The kernel needs no stamp of this kind: Kbuild already compares each object's command line on every build.
- Host packages are not affected, as they do not build with the target's flags. The exception is Rust, whose standard library has C parts built with them: the host stage's record covers it (D7).

On the toolchains' side, `toolchain-build.sh` compares the flags of the configuration with those of the record, and builds the toolchains anew when they differ (D7).

**The kernel's own skip.** Upstream skips kbuild when no file of the kernel tree is newer than the stamp of a pass's last run. But the image pass, which runs after the modules pass, writes `vmlinux.symvers`: the next modules pass took it for a change and linked the kernel again, BTF included, and so did every build, for 6.5 minutes on the VM. A second patch (`patches/openwrt/0012`, `Upstream-Status: Pending`) refreshes the modules pass's stamp once the image pass has run, as the image pass changes none of that pass's inputs. This was found during the implementation.

The patch is meant for upstream: "stamps that hold across checkouts and follow the flags". Its trailer says `Upstream-Status: Pending`, and its write-up joins the others in `docs/upstream-contributions.md`, which `toolchain-o3` turns into `docs/patches.md`. Nothing is submitted without the maintainer's consent.

Alternatives considered:
- **`CONFIG_AUTOREMOVE`**: excluded above.
- **Giving every file of a fresh checkout the commit's time**: the stamps would match, but a tree whose files went back in time could hide changed content from make. Content is the safe name.
- **A `make clean` whenever the flags change**: correct, but it relies on whoever changes the flags remembering it. With the flags in the stamps, the rebuild follows from the change itself, locally as in CI.

### D5. The patch series as commits; the tree moves once

- **The series as commits.** `scripts/lib.sh` builds each repository's patched commit in the object database, with a temporary index read from the pinned commit. For each patch it runs:
  - `git mailinfo` for the author, date, subject and body;
  - `git apply --cached`;
  - `git write-tree`;
  - `git commit-tree`, with the patch's author and date as both dates and the fixed committer.

  This is what `git am --committer-date-is-author-date` does today, so the commit is as deterministic as before. A patch that does not apply stops the step and names the patch, before any file is touched.
- **The move.** The work tree then moves to the patched commit with a single `git checkout -f --detach` from wherever it was. Git writes only the files whose content differs between the two commits, and removes those the old commit had and the new one lacks. Untracked files stay, so no clean follows: luci-base builds `po2lmo` and `jsmin` in its own source directory, and a clean, which the first plan had, removed them in every patch step, so that luci-base was built again in every build. `version.date` is written only when it changes.
- **`fetch`** fetches the pinned commits and checks them out only in a new tree. An existing tree is left for `patch` to move.

- **The other writes.** The steps after the patch keep times as well. Links that already point where they should stay; `env/wrt-boards.mk` and the toolchain's version stamp are written only when they change. A configuration the same as the one its build directories were last configured with keeps that one's time (`tmp/wrt-config-<build>`). This was found during the implementation: `make defconfig` touches `.config`, and `toolchain-build` and `config` configure the tree twice in every build. The kernel configures again when `.config`, or one of its configuration files (`env/kernel-config`, a link, among them), is newer than its configured stamp, and every kernel module's build stamp follows the kernel's `.config`. So a build with nothing changed configured the kernel and rebuilt every kernel module.

The result:
- running fetch and patch again with nothing changed writes no file;
- a changed patch rewrites only the files it changes, so only their packages rebuild;
- a lock bump rewrites only what upstream changed.

HEAD stays deterministic, so `release-publish.sh`'s check that every board was built from the same `openwrt_head` holds. The first run after the change yields new commit IDs, which nothing pins.

The alternative is to keep `git am`, save the modification times of the patched files beforehand, and restore those of unchanged content afterwards. It works, but the record has to survive from `fetch` to `patch`, and a failing series leaves a half-reset tree. Plumbing makes the move one git operation, and a failure touches nothing.

### D6. One compiler cache per stage, every language in it

- **Layout.** `$WRT_WORKDIR/compiler-cache/` holds `ccache/`, `go-build/` and `sccache/`. `link_tree` links them as the tree's `.ccache`, `.sccache` and `tmp/go-build`: the default directories of `rules.mk`, of the feed's Rust values and of its Go values. Nothing goes into the configuration, so the toolchain key does not change with the work directory. `config/ccache.conf` is linked into `ccache/` as today.
- **sccache.** `config/toolchain.seed` sets `CONFIG_RUST_SCCACHE=y`, and `flake.nix` adds sccache to the build packages. `build.sh` stops the sccache server after the build, for its statistics and so that no daemon is left behind.
- **Reports.** `build.sh` prints each cache's statistics. For ccache and sccache that is their `--show-stats`. Go has no statistics, so the report gives the number of entries in Go's cache before and after the build: a warm rebuild adds none.
- **CI.** Each stage keeps one Actions cache per run:
  - **Keys**: `compiler-cache-host-<hash>-<run>`, restored and saved only when the host stage builds, and `compiler-cache-<board>-<hash>-<run>`. The hash is that of `config/ccache.conf`, which decides whether a ccache entry can hit. Go and sccache entries carry their compiler's identity themselves.
  - **Trim**: `WRT_COMPILER_CACHE_TRIM`, replacing `WRT_CCACHE_TRIM`, drops what the build did not use:
    - ccache by its own last-use time (`--evict-older-than`);
    - Go and sccache by the files' modification times. Both refresh an entry's time when they use it: sccache on every hit, Go only when the entry is more than an hour old, so Go's cache also keeps what was modified in the hour before the build.
  - **Pruning**: the `caches` job keeps the newest compiler cache of each stage.

Each stage's cache holds all three languages, which gives one key family, one restore and save per job, and one trim rule. Separate caches per language would triple the keys without changing what is kept.

### D7. Guards for the shared toolchains

- **The record.** `toolchain-build.sh` writes `wrt-toolchain.json` with:
  - the flags, as today;
  - the hash of the C library, as today;
  - the hash of the Rust standard library for the target (`lib/rustlib/<target>/lib`).

  `toolchain-build` builds the toolchains anew when the configuration's flags differ from the recorded ones, and when a library differs from its record, as it already does for the C library. It writes the record as soon as the cross toolchain is built, and again with Rust's library, so a failed Go or Rust build keeps the cross toolchain for the next run. `build.sh` checks both libraries before and after the build.
- **No toolchain in a board's build.** `build.sh` fails, naming the stage, when the board's time log holds a stage of `tools/`, `toolchain/`, or the Go or Rust host toolchain.

A board's build that rebuilt Rust would put its `-mcpu` into the shared standard library, as one that rebuilt the C library would, and silently cost hours.

### D8. CI wiring and the budget

- **The host stage on a miss**:
  1. it restores the download cache read-only. The firmware jobs save it, and a key saved first by the host stage would lack the target sources;
  2. it restores its own compiler cache;
  3. it builds, trims and packs;
  4. it saves the archive and the compiler cache.
- **The firmware jobs** restore the download cache, their compiler cache, and the archive last, as today.
- **Budget for main**, an estimate that `docs/ci.md` replaces with measurements:

  | Cache | Size |
  |---|---|
  | Toolchain archive (Go and Rust about 0.45 GB of it) | about 1.2 GB |
  | Host compiler cache | about 1 GB |
  | Downloads | 2.7 GB |
  | Compiler cache, per board | about 1.7 GB |
  | Total, two boards | about 8.3 GB of the 10 GB quota |

  Past the quota, GitHub evicts the least recently used: superseded caches of other refs first, then main's host compiler cache. That one is saved only when the host stage builds, so it is the oldest of main's set, and losing it costs only speed.

## Risks / Trade-offs

- **[A cold host stage grows from 80 minutes to 2.5–3.5 hours, more on an EPYC 7763]** → It stays inside the 5-hour target thanks to D3. Its compiler cache brings most rebuilds down to 1–1.5 hours. D1 measures both.
- **[The stamps patch departs from upstream's choice]** → A few lines, with an `Upstream-Status: Pending` trailer and a write-up. They are a candidate for upstream as "stamps that hold across checkouts and follow the flags". Nothing is submitted without the maintainer's consent.
- **[A flag change now rebuilds every package of every board]** → That is the point: a build that keeps objects of other flags is wrong, and the flags change rarely. The compiler caches serve every flag set they have seen.
- **[The Rust patch has to follow every Rust bump of the feed]** → It touches a handful of lines. The weekly bump's patch step stops on a conflict and names the patch (build/upstream-pinning).
- **[Rust's bootstrap may not work with sccache as `RUSTC_WRAPPER`]** The feed's recipe passes it to Rust's own build too. → If bootstrap fails or ignores it, the patch drops the wrapper from Rust's own build. Rust packages keep it.
- **[Applying patches with plumbing could differ from `git am`]** → `git am` is `mailinfo`, `apply` and a commit, and the unit tests run the step on a scratch repository. The first run moves the tree to new commit IDs once.
- **[A no-change build still rebuilds something, for example through the configuration rewritten by `toolchain-build` and `config`]** → The time report shows which step. It is fixed until "Build again without changes" holds.
- **[The trim of Go and sccache relies on their refreshing an entry's time on use]** → Verified by the second CI run: a warm rebuild that shows a miss would mean the trim dropped a used entry.
- **[The cache quota]** → Trims, the `caches` job, and the eviction order described in D8. `docs/ci.md` records the measured budget.

## Migration Plan

1. **Locally**, once:
   - move `$WRT_WORKDIR/ccache` to `$WRT_WORKDIR/compiler-cache/ccache`, and the tree's `tmp/go-build` to `compiler-cache/go-build`;
   - the next build rebuilds the toolchains, under the new recipe;
   - then delete the per-board Rust left behind: `build_dir/target-*/host/rustc-*`, and Rust's files in `staging_dir/target-*/host`.
2. **In CI**, the first run builds the host stage cold under the new key and saves the new cache families. The `caches` job deletes the old `ccache-<board>-…` family along with the superseded caches.
3. **Rollback**: reverting the change brings back the old keys, and the old caches are rebuilt.
