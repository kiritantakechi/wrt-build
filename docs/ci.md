# CI

There are three workflows, all on GitHub-hosted ubuntu-24.04 runners (4-core x86_64, 6 hours max per job):

| Workflow | Job | What it does | Cache |
|---|---|---|---|
| `check.yml` | `check` | `nix develop .#quality -c just check`, whose `spec-coverage` requires every scenario of the archived specs to have its test; runs on every push, with no path filter | — |
| `check.yml` | `github-audit` | Weekly (and on demand): `just github-audit` reads back the settings the release pipeline relies on, the `release-signing` environment's reviewers and branches and the checks main requires | — |
| `build.yml` | `host-toolchain` | Fetch and patch, then build the tools and every board-neutral toolchain, in `nix develop .#build`: the cross toolchain, and Go's and Rust's on it (`just toolchain-build ci`); lists the boards of `boards/` (`just boards`) for the jobs that run per board | `staging_dir/{host,hostpkg,toolchain-*}`, `build_dir/host` and the stamps of `build_dir/hostpkg`, keyed by `scripts/toolchain-key.sh`; on a miss, the download cache (read only) and a compiler cache of its own |
| `build.yml` | `firmware` | Per board: restore the toolchains, then build the board's target code with the ci profile (all kmods), in `nix develop .#build`, failing if it compiled any part of a toolchain; produces the board's unsigned artifacts and `manifest.json` (`firmware-unsigned-<board>`) | `dl/`, and a compiler cache per board |
| `build.yml` | `caches` | After the firmware jobs, on pushes and dispatched runs: of the ref's caches it keeps the current toolchain, the newest download cache, and the newest compiler cache of each stage, the host's and each board's, and deletes the rest (`actions: write`, no build code runs) | — |
| `build.yml` | `system-test` | Per board, four jobs in parallel, each with its own emulator: `system` (`build firmware quality testing unit`), `network` (the datapath's tests behind the emulated ISP), `services` (`storage services`: the data disk, containers, SMB, VPN and metrics) and `release` (`release ops`: signing, publishing, device sync, the config push and the upgrade drill, with keys made for the run). Each downloads the board's firmware artifacts, runs `just env-report` (PPP and WireGuard for the sandbox included) and `just test <board> ci <paths>`, and uploads its JUnit report, and when a test failed, the router's console log of the whole run | — |
| `build.yml` | `sign` | Main and `bump/*` only, once `RELEASE_SIGNING` is `enabled`: waits for the maintainer's approval of the `release-signing` environment, then signs every board's firmware artifacts with the pinned signing tools (`nix run .#sign-tools -- scripts/release-sign.sh`), into `signed/<board>` | — |
| `build.yml` | `drill` | Per board: boots the board's latest stable release (`just drill-base <board>`) and drills the upgrade to its signed candidate (`just test <board> drill-base -m drill`, `WRT_SIGNED`); uploads its JUnit report, and when the drill failed, the console log | — |
| `build.yml` | `upgrade-drill` | The check main's rules require: passes when the system tests passed and every board's drill passed, or when signing, and so every drill, did not run (a pull request, or no release keys yet) | — |
| `build.yml` | `publish` | After every board's drill: `scripts/release-publish.sh --upload` with every board's signed build, a pre-release from a bump branch, the stable release from main | — |
| `bump.yml` | `bump` | Weekly: `just upstream-bump`; when upstream moved, a pull request from `bump/<date>`, and `check` and `build` started on that branch (`docs/release-flow.md`) | — |

`build.yml` runs only when code changes (changes to `openspec/`, `docs/` and Markdown files do not trigger it), and a new push to the same branch cancels the older pipeline that is still running.

The toolchain cache key depends only on these inputs: the runner architecture, the tree SHAs of openwrt's `tools/` and `toolchain/` directories, the tree SHAs of the packages feed's `lang/golang` and `lang/rust` directories, openwrt's build files that name the stamps of the Go and Rust host builds (`include/depends.mk`, `include/host-build.mk` and `rules.mk`), the board-neutral configuration composed from the profile's seeds, the build environment fingerprint `WRT_BUILD_INPUTS` (the store paths of the build packages plus the build profile; see `buildInputsId` in `flake.nix`), and the two scripts that build and pack the archive, `toolchain-build.sh` and `toolchain-pack.sh`. Each stage keeps one compiler cache, `$WRT_WORKDIR/compiler-cache` with ccache's, Go's and sccache's entries, keyed by the stage (`host`, or the board, whose packages no other board's build compiles alike), then the hash of `config/ccache.conf`'s settings, which decide whether a ccache entry can hit, then the run ID (`scripts/compiler-cache-key.sh`); its comments set nothing and stay out of the key; Go's and sccache's entries name their compiler themselves. No key carries a version number: what changes a cache's contents changes its key. So changing only the packages or luci SHA, or adding tools to the test environment, still hits the toolchain cache.

The build jobs enter `.#build`, which holds only the build environment, so they never build the emulator's QEMU: it carries a patch (`patches/qemu/`), so no binary cache has it, and building it takes a few minutes. `system-test` enters the default shell with both environments.

Only `sign` references secrets, the release keys of the `release-signing` environment, and it runs neither for a pull request nor while `RELEASE_SIGNING` is unset; every other job is also the job of a fork without secrets. `just env-report` prints the same 28 lines in CI (x86_64) and in the local VM (aarch64), checked on run 36388876907.

## Build time

Every build reports where its time went (`scripts/toolchain-build.sh`, `scripts/build.sh`). OpenWrt's build time log (`BUILD_TIME_LOG`) records when each prepare, configure, compile and install stage of each package began and ended, in the tree's `logs/build-time-<build>.tsv`: `host`, or the build directories' suffix. At the end of the build, `scripts/build-time-report.pl` prints the 15 stages that took the most time, each with two figures:
- **wall share**: each second of the build is divided among the stages that run in it, so the shares add up to the time anything ran;
- **solo time**: the seconds in which the stage ran alone, the part of the build that only a faster stage would shorten.

The report is in every build's log, CI's included. Timings measured since the build reports it come from these reports; the earlier ones below come from GitHub's timestamps on make's progress lines, which mark only when a stage began.

## Timings

| Date | Run | Stage | Duration | Notes |
|---|---|---|---|---|
| 2026-09-28 | early trial run | tools (cold cache) | about 43 min | |
| 2026-09-28 | early trial run | cross toolchain GCC 15.3.0 (cold cache) | about 35 min | |
| 2026-09-28 | 36371318405 | host-toolchain job total | 83 min | Building the tools and the toolchain: 79 min 49 s; packing and saving the cache: 6 s |
| 2026-09-28 | 36371318405 | firmware job total | 103 min | Build: 98 min 04 s (empty ccache, empty dl cache, all kmods) |
| 2026-09-28 | 36388876907 | host-toolchain job total | 81 min | The build environment fingerprint joined the key, so a cold rebuild: tools and toolchain 77 min 01 s |
| 2026-09-28 | 36388876907 | firmware job total | 138 min | Build: 131 min 45 s; ccache from the previous run, but the kernel configuration changed, so every kmod was rebuilt |
| 2026-09-28 | 36388876907 | system-test job total | 13 min | Tests: 10 min 32 s (64 tests under TCG on x86_64); failed only because `ping` was missing from the test environment |
| 2026-09-28 | 36412223299 | host-toolchain job total | 4 min 22 s | Toolchain cache hit, although `flake.nix` changed: only test packages were added, so `WRT_BUILD_INPUTS` stayed the same |
| 2026-09-28 | 36412223299 | firmware job total | 141 min | ccache from the previous run |
| 2026-09-28 | 36412223299 | system-test job total | 13 min | Tests: 8 min 04 s, 64 passed and 1 device-only skipped; spec coverage and the JUnit report (65 tests) published |
| 2026-09-28 | 36437827311 #1 | host-toolchain job total | 49 min | The key changed with the archive, which now holds the toolchain's compile stamp, so a cold rebuild |
| 2026-09-28 | 36437827311 #1 | firmware job total | 79 min | Build: 67 min on an Intel Xeon 6973P-C; the cross toolchain is no longer rebuilt; an empty cache under its new key: 2,418 of 20,837 cacheable calls hit (11.6%) |
| 2026-09-28 | 36437827311 #2 | host-toolchain job total | 4 min 30 s | Re-run of the same run: toolchain cache hit |
| 2026-09-28 | 36437827311 #2 | firmware job total | 30 min | Build: 23 min 35 s on an AMD EPYC 7763; ccache of the first attempt: 20,834 of 20,837 cacheable calls hit (99.99%) |
| 2026-09-28 | 36442399839 | system-test job total | 12 min | Tests: 10 min 03 s, 64 passed; the device target is gone, so nothing is skipped |
| 2026-09-28 | 36467421324 | host-toolchain job total | 64 min | `scripts/toolchain-build.sh` and `toolchain-pack.sh` joined the key, so a cold rebuild: tools and toolchain 53 min |
| 2026-09-28 | 36467421324 | firmware job total | 98 min | Build: 92 min; the ccache key now follows `config/ccache.conf`, so an empty cache under the new key |
| 2026-09-28 | 36467421324 | system-test job total | 48 min | Tests: 37 min 34 s, 95 passed (the A/B slots: rollback, power loss, upgrades, from the factory image through U-Boot) |
| 2026-09-29 | 36514179961 | host-toolchain job total | 75 min | A new toolchain key (the datapath changed its inputs), so a cold rebuild |
| 2026-09-29 | 36514179961 | firmware job total | 241 min | Build of the datapath (dae, einat, qosify and their kmods) on a partly matching ccache |
| 2026-09-29 | 36514179961 | system-test (system) job total | 88 min | Tests: 77 min 09 s, 121 passed |
| 2026-09-29 | 36514179961 | system-test (network) job total | 29 min | Failed: einat and qosify were not back on pppoe-wan within 180 s after restarts and a redial under TCG |
| 2026-09-29 | 36615831750 | host-toolchain job total | 10 min | Toolchain cache hit |
| 2026-09-29 | 36615831750 | firmware job total | 205 min | Build: 21,372 of 24,295 cacheable calls hit (88%); failed at the kernel configuration check: the ci profile's kmods made modules of four PCI USB drivers that `config/kernel.config` leaves out, which `config/ci.seed` now leaves out of the repository as well |
| 2026-09-30 | 36736937629 | host-toolchain job total | 64 min | The board-neutral toolchain under its new key, built cold |
| 2026-09-30 | 36736937629 | firmware (r6s) job total | 192 min | The first R6S build in CI |
| 2026-09-30 | 36736937629 | firmware (r4s) job total | 7 min | Failed: in buildbot mode two of world's sub-makes checked the toolchain's version at once, and one deleted the toolchain (`patches/openwrt/0009`) |
| 2026-10-01 | 36793323171 | host-toolchain job total | 83 min | `toolchain/` changed with patch 0009, so a cold rebuild: tools 43 min, toolchain 36 min |
| 2026-10-01 | 36793323171 | firmware (r6s) job total | 214 min | Build: 205 min on an AMD EPYC 9V74; the new compiler left the old entries behind: 4,189 of 24,288 cacheable calls hit (17%) |
| 2026-10-01 | 36793323171 | firmware (r4s) job total | 261 min | Build: 254 min, at the same hit rate |
| 2026-10-01 | 36793323171 | system-test jobs | 19 to 118 min | R6S: network 19, services 24 and system 97 min passed; release (51 min) failed, as its image trusted the attended sysupgrade CA key (`config/ci.seed`). R4S: system (118 min) passed; network (31 min) failed, qosify lost pppoe-wan after a redial (`patches/openwrt/0010`); services (33 min) was cancelled by a runner shutdown; release (84 min) failed as the R6S's did |
| 2026-10-01 | 36848242349 | host-toolchain job total | 84 min | The first run of main with patch 0009: the toolchain board-model's branch had built is not visible to main, so a cold rebuild |
| 2026-10-01 | 36848242349 | firmware (r4s) job total | 214 min | Build: 208 min on an AMD EPYC 9V74. Main's download and compiler caches had been evicted while board-model's branch ran, so both started empty: 2,868 of 24,287 cacheable calls hit (12%), within the build. Rust's host toolchain, LLVM included, took 157 min of it, the last 47 with nothing else left to build |
| 2026-10-01 | 36848242349 | firmware (r6s) job total | 284 min | Build: 280 min on an AMD EPYC 7763, from empty caches as well (12% hits). Rust's host toolchain took 211 min, the last 66 alone |
| 2026-10-01 | 36848242349 | system-test jobs | 26 to 97 min | All passed. R4S: system 92 min (173 passed, 2 skipped), release 83, services 32, network 30. R6S: system 97 min (174 passed, 1 skipped), release 48, services 34, network 26. The first green run of both boards |
| 2026-10-03 | 37143040755 | host-toolchain job total | 208 min | build-acceleration's first run, its host stage cold under a new key: the tools, the cross toolchain, and now Go and Rust, 3 h 21 min of make from an empty compiler cache (ccache: 767 of 13,292 cacheable calls hit). Rust's compile took 118 min of it, LLVM for x86_64 and aarch64 included. The archive grew to 1159 MiB, and the host stage's compiler cache was saved at 568 MiB |
| 2026-10-03 | 37143040755 | firmware (r4s) job total | 99 min | Build: 91 min on an AMD EPYC 9V74, on the restored toolchains and an empty compiler cache under its new key (ccache: 2,858 of 24,241 cacheable calls hit, 12%). No toolchain stage; the kernel's compile, 40 min, is the longest |
| 2026-10-03 | 37143040755 | firmware (r6s) job total | 82 min | Build: 74 min on an AMD EPYC 9V45, likewise (12% hits). No toolchain stage; the kernel's compile took 32 min |
| 2026-10-04 | 37143040755 | system-test jobs | 21 to 97 min | R4S: network 22, services 41 and system 73 min passed; release (84 min, its upgrade drill passed) failed on one test. R6S: network 21, services 38 and system 97 min passed; release (50 min) failed on the same test, which still gave `patch.sh` a tree that was no repository (fixed in abb3b89) |
| 2026-10-04 | 37166467868 | host-toolchain job total | 71 min | `toolchain-build.sh` changed, and with it the key, so the host stage built again, from the compiler cache run 37143040755 saved: 65 min of make, Rust's compile 29 of them (ccache: 11,342 of 26,584 cacheable calls hit; sccache: 280 of 282 Rust compiles) |
| 2026-10-04 | 37166467868 | firmware (r6s) job total | 73 min | Build: 64 min on an AMD EPYC 9V45. The new toolchain is a new compiler to ccache, which identifies it by its content, so C and C++ hit little (17%); sccache served every Rust compile (404 hits, no miss), and Go compiled anew only its 48 packages that use cgo |
| 2026-10-04 | 37166467868 | firmware (r4s) job total | 120 min | Build: 110 min on an AMD EPYC 7763, likewise (ccache 17%, sccache no miss, Go 66 packages anew) |
| 2026-10-04 | 37166467868 | system-test jobs | 28 to 118 min | All passed, the upgrade drill of both boards included: the first green run of build-acceleration. R4S: network 31, services 39, release 54, system 118 min. R6S: network 28, services 36, release 40, system 97 min. 5 h 9 min from the host stage to the last test |
| 2026-10-04 | 37181836494 | host-toolchain job total | 4 min | The key of run 37166467868: the toolchains were restored, and nothing was built |
| 2026-10-04 | 37181836494 | firmware (r4s) job total | 30 min | Build: 20 min on an Intel Xeon 6973P-C, from the compiler cache run 37166467868 made with the same toolchain: ccache served 23,782 of 23,788 cacheable calls (99.97%), sccache every Rust compile, and Go compiled one package anew. The kernel took 2 min |
| 2026-10-04 | 37181836494 | firmware (r6s) job total | 40 min | Build: 31 min on an AMD EPYC 7763, likewise: ccache 23,783 of 23,786 (99.99%), sccache no miss, Go one package anew |
| 2026-10-04 | 37181836494 | system-test jobs | 20 to 117 min | All passed. R4S: network 20, services 43, release 81, system 117 min. R6S: network 20, services 38, release 54, system 76 min. 2 h 41 min from the host stage to the last test |
| 2026-10-04 | 37220393208 | firmware jobs | 161 and 165 min | Failed. Main's first run after the merge: no download cache, and new compiler caches under the key of the changed `config/ccache.conf`. `make download` fetched Go's and Rust's sources after the toolchain was restored, newer than the restored stamps of their host builds, so each board's build built both host toolchains again, and the check that it compiles no part of the toolchain failed it. Patch 0013 makes a download an order-only prerequisite of the stamps (docs/patches.md) |
| 2026-10-05 | 37268163776 | host-toolchain and firmware jobs | 128; 140 and 105 min | toolchain-o3's first run, on its branch. `-O3` changed the board-neutral configuration, so a new toolchain key and a cold host stage; the boards' compiler caches, of the old toolchain, hit 11.7 % (R4S: build 133 min on an AMD EPYC 7763; R6S: 97 min on an AMD EPYC 9V74). Both boards built their images, then failed: the report of UB-indicative warnings found no record of base-files, which compiles without a word, so that in a fresh tree its log held only make's time line (fixed in `scripts/lib.sh`) |
| 2026-10-05 | 37293958173 | all jobs | host stage 4 min; firmware 41 and 43 min; system tests 21 to 112 min | The toolchains restored, the boards' compiler caches warm. Seven of the eight suites passed; the R4S's `system` suite failed twice. jansson's three warnings, reviewed for the R6S only, came from the R4S too (the reviews now cover both boards). And in `test_upgrade_keeps_the_configuration` the emulator reset 43 s into the new slot's trial boot, without a message, and U-Boot fell back to slot A; the same test passed in the R6S's suite and on both boards locally |

From empty caches, run 36848242349 took 7 hours 47 minutes from the host toolchain to the last system test: every firmware job compiled Rust's host toolchain, LLVM included, which no compiler cache covered, and took 3.5 to 4.75 hours. Since build-acceleration, the host stage builds every toolchain once for all boards, and each firmware job builds the board's target code alone, on a compiler cache of its own:

| Case | Run | Host stage | Firmware jobs | Host stage to last test |
|---|---|---|---|---|
| Every cache empty, the host stage's key new | 37143040755 | 208 min | 82 and 99 min | 6 h 44 min |
| The host stage's key changed, its compiler cache warm | 37166467868 | 71 min | 73 and 120 min: a new toolchain is a new compiler to ccache | 5 h 9 min |
| The toolchains restored, the board caches warm | 37181836494 | 4 min | 30 and 40 min | 2 h 41 min |

Every job stays well within its limit (330 minutes for the build jobs), and the slowest, a cold host stage, within the 5-hour target. The system tests are now the longest part of a run: the R4S's `system` suite alone takes up to two hours under TCG.

### Compiler cache

Until run 36412223299 the restored ccache hit almost nothing, for two reasons:

- ccache identified the cross compiler by its mtime, and `toolchain-unpack` gives the restored toolchain fresh mtimes on every run. `config/ccache.conf` (linked into the cache directory by `scripts/config.sh`) sets `compiler_check = content`; the key follows its settings, so the old caches, whose entries can never hit, are simply left behind.
- `make world` rebuilt the whole cross toolchain (25 to 31 min) on top of the cached one, because `toolchain/install` never writes the stamp `world` checks. `toolchain-build` now builds the stamp too, and `toolchain-pack` refuses an archive without it.

`scripts/build.sh` prints the ccache statistics of each build (OpenWrt's own go to its silenced output) and the CPU, since runners differ (an Intel Xeon 6973P-C and an AMD EPYC 7763 in the two attempts above). A ci build fills about 4.5 GB of the 12 GB the cache may grow to.

A new toolchain leaves every target entry of the old one behind, as the compiler's content changed: run 36793323171 hit 17% of its cacheable calls and grew the R6S cache from 4.7 to 9.3 GB, saved as 2.7 GB. Left alone, each board's cache would grow to its 12 GB, some 3.5 GB compressed, and the two past the quota. In CI `scripts/build.sh` therefore drops what the build did not use (`WRT_COMPILER_CACHE_TRIM`), so each board's ccache holds one build, about 1.4 GB compressed. Locally both boards share one cache, which keeps everything up to `max_size`.

Since build-acceleration, each stage's compiler cache holds every language: ccache for C and C++, Go's build cache, and sccache for Rust packages. The host stage compiles LLVM's C++ for Rust through ccache, so a host build whose inputs changed only in part is served from its cache. The trim drops ccache's entries by their last use and the others by modification time: sccache refreshes an entry on every hit, Go only one more than an hour old, so Go's cache keeps the hour before the build as well. Each build reports what every cache served: ccache's and sccache's statistics, and how many packages Go compiled anew, counted from the action entries it wrote during the build (Go keeps no statistics, and writes an entry only for an action it ran).

## Cache usage

The total cache quota for a GitHub repository is 10 GB.

| Date | Toolchain archive | Compiler caches (ccache until 2026-10-01) | dl | Nix installer | Total |
|---|---|---|---|---|---|
| 2026-09-28 | 776 MiB | 1243 MiB | 1456 MiB | 45 MiB | 3521 MiB |
| 2026-09-30 | 775 MiB | 1370 MiB per board, two boards | 2685 MiB | 45 MiB | 6245 MiB |
| 2026-10-01 | 775 MiB | 1363 and 1358 MiB, each one build's worth | 2685 MiB | 45 MiB | 6226 MiB on main, after run 36848242349's `caches` job; the merged board-model branch still held 2756 MiB, the least recently used |
| 2026-10-03 | 1159 MiB, Go and Rust included | 2081 and 2041 MiB for the boards, 568 MiB for the host stage | 2698 MiB | 46 MiB | 8547 MiB on build-acceleration's branch after run 37143040755's `caches` job, and main's Nix installer |
| 2026-10-04 | 1159 MiB | 2008 and 2009 MiB for the boards; the host stage's, evicted | 2698 MiB | 46 MiB | 7920 MiB after run 37181836494's `caches` job |

Each run saves a new compiler cache per board, and one for the host stage when it builds (their keys include the run ID), and a new download cache or toolchain whenever their inputs change (a feed's Makefile, the toolchain's key). One set takes about 8.5 GB of the 10 GB with two boards, as design D8 of build-acceleration estimated (8.3 GB); before, with ccache alone and no Go or Rust in the archive, it took 6.2 GB. Beyond the quota GitHub evicts the least recently used cache, and the firmware jobs used to restore their toolchain first: on 2026-09-30 two download caches and four ccaches pushed out the toolchain the same run's second attempt needed. The firmware jobs now restore the toolchain last, so that a download cache or ccache the run supersedes goes before it, and the `caches` job keeps one set per ref, the current toolchain and the newest download cache and compiler cache of each stage. At that usage the toolchain can stay in the cache, and there is no need to store it as a Release asset instead (the fallback in design D11). Run 36904810397 found main's set as run 36848242349 had left it: both firmware jobs restored that run's toolchain, download cache and compiler caches, and the toolchain, restored last, was the most recently used of them.

While a run saves its set beside the one it supersedes, the total passes the quota for a while, and GitHub evicts the least recently used cache. In run 37166467868 that was the host stage's compiler cache, saved early in the run and not used since. It is the one cache whose loss costs only time, as design D8 expected: the next host stage that has to build starts from an empty compiler cache, 3.5 hours instead of 1.2.
