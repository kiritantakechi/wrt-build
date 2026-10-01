# Tasks

## 1. The patch register (design D6)

- [ ] 1.1 Turn `docs/upstream-contributions.md` into `docs/patches.md`:
  - one table lists every patch file in the repository (`patches/openwrt`, `patches/packages`, `patches/qemu`, the feed packages' `patches/`, `docs/upstream`), each with its purpose, its kind (project-specific, meant for upstream, backport) and its upstream status;
  - the write-ups of the patches meant for upstream follow, as before, together with the rule that nothing is submitted without the maintainer's consent;
  - every reference to the old document points to the new one.

  Verify: `grep -r upstream-contributions` finds nothing outside the archive, and every patch file has a row.
- [ ] 1.2 Add `tests/build/test_patches.py` for the build/upstream-pinning scenarios "Patch without an entry" and "Entry without a patch": it matches the register's table against the patch files, both ways.

  Verify: the tests pass. With a row removed, or a stray patch file added, they fail and name the patch.

## 2. `-O3` for the packages, `-O2` for the kernel (design D1–D3)

- [ ] 2.1 Before anything changes, measure each board's EROFS root and upgrade image (dev profile), for D7.

  Verify: the four numbers are noted for task 2.5.
- [ ] 2.2 Set the flags in `config/toolchain.seed`:
  - `CONFIG_EXTRA_OPTIMIZATION="-fno-caller-saves -fno-plt -O3"`;
  - `CONFIG_KERNEL_CFLAGS="-O2"`;
  - `CONFIG_TARGET_OPTIMIZATION` with the target's default (`-Os -pipe -mcpu=generic`) and the UB-indicative warning options of D4.

  Update the seed's comment.

  Verify: after `just config r4s dev`, `make -s val.TARGET_CFLAGS` ends with `-O3 -mcpu=cortex-a72.cortex-a53+crypto`. The flags the kernel build adds, the extra flags without `-fno-plt` followed by the kernel's, end with `-O2`.
- [ ] 2.3 Make `scripts/build.sh` record the flags the kernel build adds (`kernel_cflags`) and the profile in the manifest. Extend `tests/firmware/test_toolchain.py`:
  - "Check compile command" expects `-O3`;
  - "Check the kernel's flags" (new) expects `-O2` last and the board's `-mcpu`;
  - "Check for relaxed floating point" (new) finds none of the relaxing options in either set of flags.

  Update `NEUTRAL_CFLAGS` in `tests/build/test_boards.py`.

  Verify: `spec-coverage --change toolchain-o3` lists the three scenarios as covered.
- [ ] 2.4 Rebuild the toolchain (`just toolchain-build dev`) and build both boards. Fix every package that fails under `-O3` in its source, with a patch registered in `docs/patches.md`. If upstream's code is right and no reasonable fix exists, opt the package out (`TARGET_CFLAGS += -O2` in its Makefile, by patch) and register it.

  Verify: both boards build, and every fix and opt-out has its row.
- [ ] 2.5 Replace `docs/lto-optouts.md` with `docs/optimization.md`:
  - the flags of D1, and why the kernel stays at `-O2`;
  - the LTO and `-O3` opt-out registers;
  - the sizes before and after (task 2.1 and now) against the 1 GiB root partition.

  Verify: every reference points to the new document, and the sizes are recorded.
- [ ] 2.6 Run the full system tests on both boards with the `-O3` builds. Trace every failure to its cause and fix it in the code that is wrong, with a registered patch.

  Verify: `just test r4s dev` and `just test r6s dev` pass, and the firmware/toolchain tests pass on both boards.

## 3. UB-indicative warnings (design D4)

- [ ] 3.1 Make `scripts/build.sh` collect the warnings of the UB-indicative options, as D4 describes. It takes the packages of the board's image from the image's package list, maps them to source packages through `tmp/.packageinfo`, parses their build logs, and writes `out/<board>/<profile>/warnings.json`.

  Verify: unit tests for the log parser (`tests/unit/`) cover a warning inside a function, one outside any function, a continuation line and an option with a value (`-Warray-bounds=`). Both boards' builds produce the report.
- [ ] 3.2 Add the register `docs/undefined-behavior.md` and `tests/quality/test_undefined_behavior.py` for the quality/undefined-behavior scenarios "Unreviewed warning" and "Stale review". Both read the build's report and the register, and match on package, option, file and function.

  Verify: with a report holding an unreviewed warning, and a register holding an entry nothing matches, each test fails and names it.
- [ ] 3.3 Triage every UB-indicative warning of both boards' builds. Undefined behavior is fixed by a patch (registered in `docs/patches.md`); a false positive is reviewed in the register, with a reason.

  Verify: the two tests pass on both boards' builds.
- [ ] 3.4 Add the test for the scenario "Check the shared flags": the manifest's package flags and kernel flags hold none of the masking options.

  Verify: it passes on both boards' builds.

## 4. The `ubsan` profile (design D5)

- [ ] 4.1 Extend `compose_seeds` in `scripts/lib.sh`:
  - seeds after a `|` in `config/profiles` apply to boards only;
  - a later seed's line for a symbol replaces an earlier one, which generalizes today's merge of `CONFIG_EXTRA_OPTIMIZATION`.

  Verify: tests in `tests/build/test_boards.py`:
  - the toolchain composition of a profile with board-only seeds equals that of the profile without them, so their toolchain keys are equal;
  - a composed board seed holds one line per symbol, the later seed's;
  - `just config r4s dev` still passes its seed check.
- [ ] 4.2 Add the `ubsan` profile and `config/ubsan.seed` (`CONFIG_TARGET_OPTIMIZATION` plus `-fsanitize=undefined -fsanitize-trap=undefined`). `scripts/config.sh` suffixes the build directories of a profile with board-only seeds with the profile (`r4s_ubsan`), and its outputs go to `out/<board>/ubsan`.

  Verify: after `just config r4s ubsan`, `TARGET_CFLAGS` holds the sanitizer flags while the kernel's flags do not, `BUILD_SUFFIX` is `r4s_ubsan`, and the toolchain key equals the dev profile's.
- [ ] 4.3 Add the feed package `wrt-ubsan-probe`, which overflows a signed integer on purpose; only `config/ubsan.seed` selects it.

  Verify: it builds in the `ubsan` profile, and the dev and ci images do not contain it (`scripts/image-audit.sh` refuses it).
- [ ] 4.4 Detect traps in the harness. In a build whose manifest names the `ubsan` profile, the router fixture reads the kernel log for user-space traps before it restores the snapshot, and fails the test with the process name and address. Add the test for the scenario "Trap during a system test": it runs the probe and expects the trap to be reported. It skips in other profiles.

  Verify: on a `ubsan` build the scenario's test passes, and a test that runs the probe without expecting the trap fails, naming `wrt-ubsan-probe`.
- [ ] 4.5 Build and test both boards in the `ubsan` profile (`just build <board> ubsan`, `just test <board> ubsan`). Fix every trap in the code that is wrong, with a patch registered in `docs/patches.md`. Document in `docs/undefined-behavior.md` how to run the profile, and when: after an upstream bump, and before a stable release.

  Verify: both boards' suites pass under the `ubsan` profile, with no trap, and the run is logged in the document.

## 5. Patch audit (design D6)

- [ ] 5.1 Drop patch 0002: the A/B boot environment (`uboot/wrt-ab.env`) passes `fstools_overlay_compression_type=zstd` already.

  Verify: the firmware/rootfs test "First boot creates the overlay" passes on both boards, and the register no longer lists 0002.
- [ ] 5.2 Re-derive BBRv3 from its primary source: the google/bbr v3 branch as Oleksandr Natalenko rebases it onto 6.18. Compare it with the current series, explain or remove every difference, and record the source and the comparison in the register.

  Verify: the kernel builds on both boards, and the firmware/kernel scenario "BBRv3 as default congestion control" passes on both.
- [ ] 5.3 Review every other patch against the current pins: 0003–0010, the packages patch, einat's patch, QEMU's patch, and the two prepared upstream patches. For each, check:
  - still needed (not upstream, not dead);
  - minimal and correct;
  - its message accurate and current, with `Signed-off-by`;
  - for C, clean under the warnings and the UBSan run.

  Refresh what falls short, and record the result per patch in the register.

  Verify: `just patch` applies the series. The tests that cover each patch's behavior pass on both boards (named in its row), and QEMU builds with its patch.

## 6. Integration

- [ ] 6.1 With everything in place, run the full system tests on both boards (dev profile).

  Verify: all tests pass on both boards, and `spec-coverage --change toolchain-o3` reports no uncovered scenario.
- [ ] 6.2 Get a green CI run for both boards.

  Verify: record the run and its per-board timings in `docs/ci.md`: the cold toolchain and compiler cache of the first run, and the cache hits of the second.
