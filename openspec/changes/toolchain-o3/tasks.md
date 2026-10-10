# Tasks

## 1. Every patch states its upstream status (design D6)

- [x] 1.1 Give every patch file in the repository its `Upstream-Status` trailer: `patches/openwrt`, `patches/packages`, `patches/qemu`, the feed packages' `patches/` and `docs/upstream`. A `git format-patch` patch carries it at the end of its message, a plain diff in its header. The audit of group 5 refines the statuses; until then, they hold what the patch is today.

  Verify: `git interpret-trailers --parse` finds the trailer in every format-patch file, and every plain diff's header has it.
- [x] 1.2 Turn `docs/upstream-contributions.md` into `docs/patches.md`:
  - the trailer convention: its vocabulary, where the trailer goes in each kind of patch file, and that a patch's number is its identity, never reused or shifted;
  - the write-ups of the `Pending` and `Submitted` patches, as before, with the rule that nothing is submitted without the maintainer's consent;
  - every reference to the old document points to the new one.

  Verify: `grep -r upstream-contributions` finds nothing outside the archive.
- [x] 1.3 Add `tests/build/test_upstream_pinning.py` for the build/upstream-pinning scenarios "Patch without a status", "Patch meant for upstream without a write-up" and "Write-up without a patch". It reads every patch file's trailer, and matches the `Pending` and `Submitted` patches against the write-ups, both ways.

  Verify: the tests pass. With a trailer removed, a status outside the vocabulary, a write-up removed or a stray one added, they fail and name the patch or the write-up.

## 2. `-O3` for the packages, `-O2` for the kernel (design D1–D3)

- [x] 2.1 Before anything changes, measure each board's EROFS root and upgrade image (dev profile), for D7.

  Verify: the four numbers are noted for task 2.5.
- [x] 2.2 Set the flags in `config/toolchain.seed`:
  - `CONFIG_EXTRA_OPTIMIZATION="-fno-caller-saves -fno-plt -O3"`;
  - `CONFIG_KERNEL_CFLAGS="-O2"`;
  - `CONFIG_TARGET_OPTIMIZATION` with the target's default (`-Os -pipe -mcpu=generic`) and the UB-indicative warning options of D4.

  Update the seed's comment.

  Verify: after `just config r4s dev`, `make -s val.TARGET_CFLAGS` ends with `-O3 -mcpu=cortex-a72.cortex-a53+crypto`. The flags the kernel build adds, the extra flags without `-fno-plt` followed by the kernel's, end with `-O2`.
- [x] 2.3 Make `scripts/build.sh` record the flags the kernel build adds (`kernel_cflags`) and the profile in the manifest. Extend `tests/firmware/test_toolchain.py`:
  - "Check compile command" expects `-O3`;
  - "Check the kernel's flags" (new) expects `-O2` last and the board's `-mcpu`;
  - "Check for relaxed floating point" (new) finds none of the relaxing options in either set of flags.

  Update `NEUTRAL_CFLAGS` in `tests/build/test_boards.py`.

  Verify: `spec-coverage --change toolchain-o3` lists the three scenarios as covered.
- [x] 2.4 Build both boards in the existing tree: `build-acceleration`'s stamps rebuild the toolchains and every package with the new flags. Fix every package that fails under `-O3` in its source, with a patch stating its upstream status. If upstream's code is right and no reasonable fix exists, opt the package out (`TARGET_CFLAGS += -O2` in its Makefile, by patch) and record the opt-out in `docs/optimization.md`.

  Verify: both boards build, and every fix and opt-out has its row.
- [x] 2.5 Replace `docs/lto-optouts.md` with `docs/optimization.md`:
  - the flags of D1, and why the kernel stays at `-O2`;
  - the LTO and `-O3` opt-out registers;
  - the sizes before and after (task 2.1 and now) against the 1 GiB root partition.

  Verify: every reference points to the new document, and the sizes are recorded.
- [x] 2.6 Run the full system tests on both boards with the `-O3` builds. Trace every failure to its cause and fix it in the code that is wrong, with a patch stating its upstream status.

  Verify: `just test r4s dev` and `just test r6s dev` pass, and the firmware/toolchain tests pass on both boards.

## 3. UB-indicative warnings (design D4)

- [x] 3.1 Make `scripts/build.sh` collect the warnings of the UB-indicative options, as D4 describes. It takes the packages of the board's image from the image's package list, maps them to source packages through `tmp/.packageinfo`, parses their build logs, and writes `out/<board>/<profile>/warnings.json`.

  Verify: unit tests for the log parser (`tests/unit/`) cover a warning inside a function, one outside any function, a continuation line and an option with a value (`-Warray-bounds=`). Both boards' builds produce the report.
- [x] 3.2 Add the register `tests/reviewed-warnings.toml` and `tests/quality/test_undefined_behavior.py` for the quality/undefined-behavior scenarios "Unreviewed warning" and "Stale review". Both read the build's report and the register, and match on package, option, file and function. Add `docs/undefined-behavior.md`: how a warning is reviewed and recorded.

  Verify: with a report holding an unreviewed warning, and a register holding an entry nothing matches, each test fails and names it.
- [x] 3.3 Triage every UB-indicative warning of both boards' builds. Undefined behavior is fixed by a patch, its status `Pending`; a false positive is reviewed in `tests/reviewed-warnings.toml`, with a reason.

  Verify: the two tests pass on both boards' builds.
- [x] 3.4 Add the test for the scenario "Check the shared flags": the manifest's package flags and kernel flags hold none of the masking options.

  Verify: it passes on both boards' builds.

## 4. The `ubsan` profile (design D5)

- [x] 4.1 Extend `compose_seeds` in `scripts/lib.sh`:
  - seeds after a `|` in `config/profiles` apply to boards only;
  - a later seed's line for a symbol replaces an earlier one, which generalizes today's merge of `CONFIG_EXTRA_OPTIMIZATION`.

  Verify: tests in `tests/unit/test_lib.py`, beside the other tests of `scripts/lib.sh` (no build/boards scenario covers the composition):
  - the toolchain composition of a profile with board-only seeds equals that of the profile without them, so their toolchain keys are equal;
  - a composed board seed holds one line per symbol, the later seed's;
  - `just config r4s dev` still passes its seed check.
- [x] 4.2 Add the `ubsan` profile and `config/ubsan.seed` (`CONFIG_TARGET_OPTIMIZATION` plus `-fsanitize=undefined -fsanitize-trap=undefined`). `scripts/config.sh` suffixes the build directories of a profile with board-only seeds with the profile (`r4s_ubsan`), and its outputs go to `out/<board>/ubsan`.

  Verify: after `just config r4s ubsan`, `TARGET_CFLAGS` holds the sanitizer flags while the kernel's flags do not, `BUILD_SUFFIX` is `r4s_ubsan`, and the toolchain key equals the dev profile's.
- [x] 4.3 Add the feed package `wrt-ubsan-probe`, which overflows a signed integer on purpose; only `config/ubsan.seed` selects it.

  Verify: it builds in the `ubsan` profile, and the dev and ci images do not contain it (`scripts/image-audit.sh` refuses it).
- [x] 4.4 Detect traps in the harness. In a build whose manifest names the `ubsan` profile, the router fixture reads the kernel log for user-space traps before it restores the snapshot, and fails the test with the process name and address. Add the test for the scenario "Trap during a system test": it runs the probe and expects the trap to be reported. It skips in other profiles.

  Verify: on a `ubsan` build the scenario's test passes, and a test that runs the probe without expecting the trap fails, naming `wrt-ubsan-probe`.
- [x] 4.5 Build and test both boards in the `ubsan` profile (`just build <board> ubsan`, `just test <board> ubsan`). Fix every trap in the code that is wrong, with a patch, its status `Pending`. Document in `docs/undefined-behavior.md` how to run the profile, and when: after an upstream bump, and before a stable release.

  Verify: both boards' suites pass under the `ubsan` profile, with no trap, and the run is logged in the document.

## 5. Patch audit (design D6)

- [x] 5.1 Drop patch 0002: the A/B boot environment (`uboot/wrt-ab.env`) passes `fstools_overlay_compression_type=zstd` already.

  Verify: the firmware/rootfs test "First boot creates the overlay" passes on both boards, and no patch takes the number 0002.
- [x] 5.2 Re-derive BBRv3 from its primary source: the google/bbr v3 branch as Oleksandr Natalenko rebases it onto 6.18. Compare it with the current series, and explain or remove every difference. Its trailer names the source (`Backport [...]`), and its message the comparison.

  Verify: the kernel builds on both boards, and the firmware/kernel scenario "BBRv3 as default congestion control" passes on both.
- [x] 5.3 Review every other patch against the current pins: the series from 0003 on (`build-acceleration`'s 0011 and 0012 included), the packages patches, einat's patch, QEMU's patch, and the two prepared upstream patches. For each, check:
  - still needed (not upstream, not dead);
  - minimal and correct;
  - its message accurate and current, with `Signed-off-by`;
  - for C, clean under the warnings and the UBSan run.

  Refresh what falls short, and set each patch's trailer to its status after the review.

  Verify: `just patch` applies the series. The tests that cover each patch's behavior pass on both boards (named in its message), and QEMU builds with its patch.

- [x] 5.4 Fix each fault the `-O3` and UBSan work found where it lies, without trading generality away (`docs/patches.md`, "What a patch fixes"), and drop the workarounds that stood in for those fixes:
  - mold claims LTO objects in the command line order (0018), instead of linking LTO packages on one thread;
  - libtool passes every sanitizer option to the link (0019), the packages' own copies of libtool get the same change in a build that sanitizes (0021), and packages link with the sanitizer options they compile with (0017), instead of building trap builds without LTO and answering `-lubsan` with an empty archive;
  - lto-wrapper writes each LTRANS job's output whole (0020), and a parallel package's make each job's (0016), instead of running LTRANS jobs one after another (`-flto=1`).

  Verify: links of the same LTO objects with mold give the same output, with its threads; the `ubsan` builds keep LTO, and no file of their root filesystems calls into a runtime; and every build of a board reports the same warnings.

## 6. Integration

- [x] 6.1 With everything in place, run the full system tests on both boards (dev profile).

  Verify: all tests pass on both boards, and `spec-coverage --change toolchain-o3` reports no uncovered scenario.
- [x] 6.2 Keep a restored toolchain up to date when the download cache misses: main's run 37220393208 rebuilt Go's and Rust's host toolchains in both firmware jobs, as `make download` fetched their sources after the toolchain's stamps were restored. Patch 0013 makes a download an order-only prerequisite of the prepared stamps, with its write-up in `docs/patches.md`, and the run is recorded in `docs/ci.md`. The same run compiled cold under new compiler cache keys, as an edit of `config/ccache.conf`'s comments changed them: the keys now hash its settings only (`scripts/compiler-cache-key.sh`).

  Verify: on the VM, with Go's source made newer than its host build's prepared stamp, Go's host build is prepared again without the patch and is up to date with it.
- [x] 6.3 Get a green CI run for both boards.

  Verify: record the run and its per-board timings in `docs/ci.md`: the cold toolchain and compiler cache of the first run, and the cache hits of the second.
