# Tasks

## 1. Measure every build (design D1)

- [ ] 1.1 Record and report the build time log:
  - `scripts/toolchain-build.sh` and `scripts/build.sh` export `BUILD_TIME_LOG=$TREE/logs/build-time-<stage>.tsv`, where the stage is `host` or the board, emptied before make runs;
  - after make, whether it succeeded or not, they print `scripts/build-time-report.pl -n 15` of it.

  Add a "Build time" section to `docs/ci.md`: what the report shows, wall share and solo time, and that the timings below come from it. Add the build/environment scenario "Find what holds up a build" to `tests/verified-elsewhere.toml`.

  Verify: `just build r4s dev` on the VM ends with the report, and `logs/build-time-r4s.tsv` holds the record.
- [ ] 1.2 Before anything else changes, take the baseline on the VM:
  - `just build r4s dev` twice in a row;
  - the second run's duration and its report's top stages.

  Note both in `docs/dev-setup.md` (section 4, Build) as the starting point.

  Verify: the second report shows the kernel's prepare and compile stages that this change removes.

## 2. Rebuild only what changed (design D4, D5)

- [ ] 2.1 Add `patches/openwrt/0011`: `PKG_FILES_MD5` (`include/depends.mk`) and the kernel's prepared stamp (`include/kernel-build.mk`) always hash content (`find_md5_reproducible`). Register it in `docs/upstream-contributions.md` as meant for upstream and not submitted, with its write-up.

  Verify:
  1. In a built tree, set every file of `feeds/packages/lang/golang` to an older time, keeping its content.
  2. Run `make package/feeds/packages/golang/host/compile` again; its time log shows no prepare stage.
  3. Without the patch, the same check prepares again.
- [ ] 2.2 In `scripts/lib.sh`, build a repository's patched commit in the object database, and move a work tree to a commit (D5):
  - `patch.sh` builds each repository's commit, then moves its tree once;
  - `fetch.sh` fetches the pinned commits and checks them out only in a new tree;
  - the usage lines and comments of both scripts say what they now do.

  Verify: on the VM, `just fetch patch` twice in a row leaves no file of the tree newer than a marker file touched in between, and the HEADs are the same both times.
- [ ] 2.3 Add tests for the build/environment requirement "Rebuild only what changed" to `tests/build/test_environment.py`. They run the helpers of 2.2 on a scratch repository with a series of two patches:
  - "Re-apply an unchanged series": no file's modification time changes;
  - "Change one patch": exactly the files whose content changed get a new time;
  - "A patch that does not apply": the step fails naming the patch, and no file changes.

  Verify: the three tests pass, and fail against the old `git am` path.
- [ ] 2.4 Make a no-change build compile nothing: run `just build r4s dev` twice, and fix whatever the second build's report still prepares, configures or compiles, for example a step that follows the configuration that `toolchain-build` and `config` rewrite. Add "Build again without changes" to `tests/verified-elsewhere.toml`. Note the new duration next to the baseline of 1.2.

  Verify: the second build's report lists no prepare, configure or compile stage, and the build takes minutes.

## 3. Every toolchain in the host stage (design D2, D3, D7)

- [ ] 3.1 Add `patches/packages/0002` for the feed's Rust recipe:
  - it builds in `build_dir/hostpkg` and installs into `staging_dir/hostpkg`, its uninstall script included;
  - `llvm.targets` holds only the host's and the target's backends, and `llvm.experimental-targets` is empty;
  - with `CONFIG_CCACHE`, `llvm.ccache` is set.

  If Rust's bootstrap fails, or ignores sccache as `RUSTC_WRAPPER`, the patch drops the wrapper from Rust's own build (design, risks).

  Verify: `staging_dir/hostpkg/bin/rustc -vV` runs, and `staging_dir/hostpkg/lib/rustlib/aarch64-unknown-linux-musl` exists. LLVM's CMake cache in the build directory lists the two backends. The host report shows Rust's stages.
- [ ] 3.2 Make `scripts/toolchain-build.sh` build the Go and Rust host toolchains after the tools and the cross toolchain. Its record, `wrt-toolchain.json`, gains the hash of the Rust standard library for the target. A toolchain whose library differs from its record is built anew, as the C library already is.

  Verify:
  - after `just toolchain-build dev`, the record names both libraries;
  - a second run's report holds no compile stage;
  - after the Rust library is changed by hand, the next run builds Rust again.
- [ ] 3.3 Make `scripts/toolchain-pack.sh` pack `staging_dir/hostpkg` and the stamps of `build_dir/hostpkg` (the empty dot files), and `scripts/toolchain-unpack.sh` touch them with the rest.

  Verify, on the VM:
  1. pack the archive;
  2. delete `staging_dir/hostpkg` and `build_dir/hostpkg`;
  3. set every source file of the tree to the current time, as a fresh checkout would;
  4. unpack.

  Then `make package/feeds/packages/golang/host/compile package/feeds/packages/rust/host/compile` does nothing.
- [ ] 3.4 Guard the shared toolchains (D7):
  - `scripts/build.sh` checks the C and Rust libraries against the record before and after the build;
  - it fails, naming the stage, when the board's time log holds a stage of `tools/`, `toolchain/` or a Go or Rust host toolchain. Put that check in a `scripts/lib.sh` helper over the log.

  Tests:
  - extend `tests/build/test_boards.py`: "A toolchain built for a board" covers the Rust library;
  - add "Boards share the toolchains", unit-testing the helper on a sample log;
  - rename the requirement in the file's `@spec` markers to "The same toolchains for every board".

  Verify: the tests pass. Build r4s, then r6s, on the VM: neither report holds a toolchain stage.
- [ ] 3.5 Update `docs/dev-setup.md` (section 4): the boards share every toolchain, and a board's first build no longer builds Rust. Under the migration plan, list the per-board Rust leftovers that may be deleted, and delete them on the VM.

  Verify: `build_dir/target-*/host/rustc-*` is gone, and both boards still build without a toolchain stage.

## 4. A compiler cache for every language (design D6)

- [ ] 4.1 Lay out the compiler caches:
  - add sccache to the build packages in `flake.nix`;
  - set `CONFIG_RUST_SCCACHE=y` in `config/toolchain.seed`, with a comment;
  - `link_tree` links `$WRT_WORKDIR/compiler-cache/{ccache,go-build,sccache}` as the tree's `.ccache`, `tmp/go-build` and `.sccache`, and `config/ccache.conf` into `ccache/`.

  On the VM, move the existing ccache and Go cache there. Document the layout and the move in `docs/dev-setup.md`.

  Verify: after `just config r4s dev`, the three links resolve into `compiler-cache`, and `nix develop .#build -c sccache --version` runs.
- [ ] 4.2 Make `scripts/build.sh` report every cache:
  - ccache's and sccache's `--show-stats`;
  - the number of Go cache entries before and after the build;
  - and it stops the sccache server afterwards.

  Verify: build r4s, then clean and rebuild `einat` and `dae`. The second build reports sccache hits and no new Go entries.
- [ ] 4.3 Trim every compiler cache in CI: `WRT_COMPILER_CACHE_TRIM` replaces `WRT_CCACHE_TRIM`. ccache evicts by its own last use, and Go and sccache drop files not modified since the build began. Put the file trim in a `scripts/lib.sh` helper with a unit test in `tests/unit/test_lib.py` over files of different ages.

  Verify: the unit test passes, and `grep -r WRT_CCACHE_TRIM` finds nothing outside the archive.
- [ ] 4.4 Update the build/environment records in `tests/verified-elsewhere.toml`:
  - "Build directory on an external volume" names the compiler caches of every language;
  - "A new source tree" is added, proven by every CI job, which starts from a fresh tree and restored caches.

  Verify: `spec-coverage --change build-acceleration` lists both as covered.

## 5. CI (design D8)

- [ ] 5.1 Update `.github/workflows/build.yml`:
  - the host-toolchain job, on a miss, restores the download cache without saving it, restores `compiler-cache-host-…`, builds, trims, packs, and saves the archive and its compiler cache;
  - the firmware jobs use `compiler-cache-<board>-…` with `WRT_COMPILER_CACHE_TRIM`, and restore the archive last;
  - the `caches` job keeps the newest compiler cache of each stage and deletes the old `ccache-…` family;
  - the workflow's header comments match.

  Verify: actionlint passes, and `just check` is green.
- [ ] 5.2 Get a first green run, with a cold host stage. Record in `docs/ci.md`:
  - each stage's duration and report;
  - the firmware jobs' durations per board, with their CPU;
  - that no firmware report holds a toolchain stage.

  Update the build/ci records in `tests/verified-elsewhere.toml` for "Toolchain cache hit", "Only the packages feed updated" and "Toolchain inputs change".

  Verify: the run is green, and the records cite it.
- [ ] 5.3 Dispatch a second run of the same commit (`workflow_dispatch`). From its firmware reports, record that no compiler cache missed and that Go's gained no entry. Then record the cache budget after the `caches` job (`gh cache list`) against the estimate of D8. Add "Rebuild from warm compiler caches" and "One compiler cache per stage" to `tests/verified-elsewhere.toml`.

  Verify: the second run's firmware jobs take under an hour, and the ref holds one compiler cache per stage.
- [ ] 5.4 Rewrite the stage, cache and timing sections of `docs/ci.md`:
  - what the host stage builds;
  - the compiler caches per stage and their trim;
  - the measured budget;
  - the cold and warm durations, in place of "well within the 6-hour limit".

  Verify: every figure in the text cites a run.

## 6. Integration

- [ ] 6.1 On images built after the change, run the full suites of both boards on the VM (`just test r4s dev`, `just test r6s dev`), and the system tests in CI.

  Verify: all pass, and `spec-coverage --change build-acceleration` reports no uncovered scenario.
