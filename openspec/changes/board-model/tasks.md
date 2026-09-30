# Tasks

## 1. Board descriptions and their model (design D1)

- [x] 1.1 Add `boards/r4s.json` and `boards/r6s.json` with the fields of design D1.
  - Values for the R4S come from today's constants in `emu.py`, `test_rootfs.py`, `test_kernel.py` and `emulation.yaml`.
  - Values for the R6S come from the upstream tree: device and board name (`armv8.mk`, `02_network`), U-Boot variant and board directory, and port controllers from `rk3588s-nanopi-r6.dtsi`. The loader's signature is confirmed by task 3.6.

  Verify: both files are valid JSON, and every field of design D1 is present.
- [x] 1.2 Add the strict pydantic model `tests/wrt_tests/boards.py` (`Board`, loading by id and all boards), and add pydantic to `tests/pyproject.toml` and `uv.lock`.

  Verify: `tests/unit/test_boards.py` loads both descriptions, and rejects copies with a missing field and with a wrongly typed field, naming the board and the field.
- [x] 1.3 Board helpers:
  - add `scripts/boards.sh` (`just boards`, which prints the board ids as JSON, and checks the boards it is given);
  - add `board_field <id> <path>` to `scripts/lib.sh`, which dies naming the known boards on an unknown id;
  - add a `boards` check to `scripts/check.sh`, which loads every description with the model.

  Verify: `just boards` prints `["r4s","r6s"]`. `tests/build/test_boards.py` covers "A malformed description": `just check boards` on a copy of the repository with a broken description fails, naming the board and the field.

## 2. One build per board from one tree (design D2)

- [x] 2.1 Rework `scripts/config.sh <board> <profile>`:
  - compose the profile's seeds, then a board seed generated from the description: device, `CONFIG_EXTRA_OPTIMIZATION` with the board's `-mcpu`, `CONFIG_BUILD_SUFFIX` and `CONFIG_BINARY_FOLDER`;
  - reduce `config/target.seed` to the target and subtarget;
  - drop `-mcpu` from `config/toolchain.seed`.

  Verify: `just config r6s ci` yields a `.config` with the R6S device, its `-mcpu`, `BUILD_SUFFIX="r6s"` and `BINARY_FOLDER` under `bin/r6s`. `tests/build/test_boards.py` covers "Build an unknown board": `just build nope`, and `config`, `test` and `drill-base` with it, fail before touching the work directory, naming `r4s` and `r6s`.
- [x] 2.2 Make the toolchain board-neutral:
  - `scripts/toolchain-build.sh` configures the tree for every board's device and none of their `-mcpu`, and records `TARGET_CFLAGS` and the C library's hash in `wrt-toolchain.json` in the toolchain directory;
  - `scripts/build.sh` refuses a toolchain with no record, one holding a board's `-mcpu`, or one whose C library is not the recorded one, before and after the build;
  - a local `just build` runs `toolchain-build` first.

  Verify: `tests/build/test_boards.py` covers "Toolchain free of board flags", using the `toolchain_cflags` each build's manifest records (task 2.3). "A toolchain built for a board": `build.sh` on a stand-in tree fails without building when the toolchain has no record, a record holding a board's `-mcpu`, or another C library.
- [x] 2.3 Make `scripts/build.sh` per board:
  - find the board's kernel and U-Boot build directories through its `BUILD_SUFFIX`, with no globs over `target-*`;
  - copy `bin/<id>` to `out/<board>/<profile>`, saving the board's U-Boot configuration as `u-boot.config` and the emulator's as `u-boot-qemu.config`;
  - record `board` and `toolchain_cflags` in `manifest.json`.

  Verify: `tests/build/test_boards.py` covers "Two boards in one tree": each build's outputs sit in `out/<board>/<profile>`, and each diffconfig carries its own `BUILD_SUFFIX` and `BINARY_FOLDER`. The build/ci scenario "Complete manifest" gets a test in place of its manual verification (`tests/build/test_ci.py`): the manifest names the board the images were built for, and its vermagic is the image kernel's and the kmods'.
- [x] 2.4 Make the `justfile` recipes `config`, `build` and `test` take `<board> [profile]`, `drill-base` take `<board>`, and add `boards`; `scripts/test.sh` takes the board. Update `docs/dev-setup.md`: the commands, and the roughly 45 GB a second board adds to `$WRT_WORKDIR`.

  Verify: `just --list` shows the new signatures, the skeleton check passes, and the documented commands run as written.
- [x] 2.5 Replace the manual verification of the firmware/toolchain scenario "Check compile command" (`tests/verified-elsewhere.toml`) with a test. `build.sh` records in the manifest the flags every target package compiles with (`TARGET_CFLAGS`), and `tests/firmware/test_toolchain.py` checks that `-O2` and the board's `-mcpu` come after `-Os`.

  Verify: the test passes on each board's build.
- [x] 2.6 Key the toolchain cache on the board-neutral configuration `compose_seeds` writes for the profile (`just toolchain-key <profile>`), not on `toolchain.seed` alone. Have `toolchain-build` build anew a toolchain whose C library is not the one its record names, rather than record it again, and write the version stamp that buildbot mode checks. Carry an OpenWrt patch that makes that check safe for the concurrent sub-makes of a parallel build (`patches/openwrt/0009`). The host-toolchain job's `Boards` step fails when `just boards` does.

  Verify: the build/boards tests "Rebuild a changed toolchain", "Keep the toolchain in buildbot mode" and "Check the version from parallel makes" pass: a stand-in toolchain whose C library differs from its record, or that has none, is built anew, one as recorded is kept, and each names the last commit of `toolchain/`; makes started a millisecond apart run the patched check at once and keep a toolchain of the right version, and still delete one of another. On the local tree, `just config <board> ci` after a dev build keeps the toolchain and the build directories. actionlint passes, and a CI run's host-toolchain job builds or restores the toolchain under the new key, and both firmware jobs build on it.
- [x] 2.7 Make "Two boards in one tree" check what separates the builds, beyond each build's own record: each board's build directory holds its own U-Boot and no other board's, and the tree's output directory of each board holds its own images alone, still those of its manifest.

  Verify: the test passes with both boards built in one tree.

## 3. Bootloader, images and the R6S (design D3–D5)

- [x] 3.1 Move the environment location (`ENV_IS_IN_MMC`, offset `0x3F8000`, size `0x8000`) into `uboot/wrt-ab.config`, with `ENV_MMC_DEVICE_INDEX` in each `board-*.config`. Add `uboot/board-r6s.env` (eMMC `mmc1`, console `ttyS2` at `0xfeb50000`, `bootm`) and `uboot/board-r6s.config` (DesignWare watchdog, 60 s).

  Verify: the firmware/boot-rollback test for "Compare the two bootloaders" passes for the board under test: identical logic, and the environment on the MMC device of the constants at the shared offset.
- [x] 3.2 Reduce patch 0003 to one include of `wrt-ab.mk` after the variants' definitions, whose hook, evaluated for `$(BUILD_VARIANT)`, extends the variant of a board. The tree scripts write `env/wrt-boards.mk` (variant, id and environment directory, and the devices) from the descriptions, and `uboot/wrt-ab.mk` looks the variant up in it.

  Verify: `make -C "$TREE" -s val.UBOOT_CONFIG` (or the variant's configure step) shows the fragments for `nanopi-r4s-rk3399` and `nanopi-r6s-rk3588s`, and none for another variant. Both boards' U-Boot builds carry `wrt.env`. The patch names no board.
- [x] 3.3 Rework patch 0004: `Device/Default` applies `Device/wrt-ab` to the devices of `WRT_AB_DEVICES` from `env/wrt-boards.mk`, instead of per-device lines. The R4S Enterprise edition drops out.

  Verify: both boards' builds produce `*-factory.img.gz` and `*-sysupgrade.tar.gz`, and the firmware/ab-layout tests pass on the R4S build.
- [x] 3.4 Drop patch 0006. wrt-ab installs a uci-defaults script that configures `/etc/config/ubootenv` for the boot disk at the shared offset whenever `wrt.slot` is on the command line.

  Verify: `fw_printenv` reads the slot variables in the emulator, and the firmware/ab-upgrade and boot-rollback tests that read and write the environment pass.
- [x] 3.5 Rewrite patch 0005: the root partition's number comes from its sysfs `partition` attribute, the device resolved from `PARTUUID` through sysfs uevents, with no arithmetic on parsed text.

  Verify: the config-preserving upgrade tests of firmware/ab-upgrade pass, and the patch parses no digits out of a UUID.
- [x] 3.6 Build the R6S (`just build r6s dev`). Confirm its description's loader signature on the factory image, and its device-tree nodes on the built kernel FIT. Make the firmware/rootfs test "Complete boot chain" (renamed marker) read the loader signature, board name, SoC and nodes from the description.

  Verify: it passes on both boards' factory images.
- [x] 3.7 Make the firmware/kernel tests "Drivers for the board's ports" (renamed marker) read the description's drivers, and "Shipped kernel boots in the emulator" name the boot disk.

  Verify: both pass on both boards.
- [x] 3.8 Update the docs:
  - `docs/ab-layout.md`: the boot disk per board;
  - `docs/migration-single-to-ab.md`: the R6S's first install on the eMMC, from an SD-booted system or over USB in maskrom mode, and maskrom recovery;
  - `docs/supply-chain`: rkbin's DDR blob in the R6S loader;
  - `docs/kernel.md`: one kernel for both boards.

  Verify: each page covers both boards, and its commands match the recipes.

## 4. The emulator and the sandbox per board (design D7, D8)

- [x] 4.1 `emu-prepare` writes the labgrid target description from the board (CPU, cores, memory, `sd-card` or `emmc` on `sdhci-pci` with its size, one NIC per port in order on its segment's tap, watchdog, xHCI) and stamps the device tree with the board's name and model. `tests/targets/emulation.yaml` goes away, and `scripts/test.sh` uses the generated description.

  Verify: the testing/emulation tests "Verify artifact provenance", "Read board name" (renamed marker) and "Run userspace programs" pass on both boards.
- [x] 4.2 Build the sandbox topology in `wrt_tests.net` from the board's ports: WAN on `br-wan`, the first LAN port on `br-lan`, and a second LAN port on `br-lan2` with `client-c`.

  Verify: "LAN client gets an address" passes on both boards, and the new "Clients on both LAN ports share one LAN" test passes on the R6S and skips on the R4S.
- [x] 4.3 Add a session fixture `board`, from the build manifest. Replace the R4S constants of the tests and helpers with the description's facts: `test_boot_rollback`, `test_emulation`, `test_ab_upgrade` (board check), `test_monitoring`, `wrt_tests.ab`, `wrt_tests.emu`. Move the FIT unit test's sample to a neutral board name.

  Verify: `just test r4s dev` passes as it did before the change, and `spec-coverage` reports no dangling markers.
- [x] 4.4 Give the emulated cores the SoC's capacities: the descriptions hold each core's `capacity-dmips-mhz` from the upstream device trees (`soc.cores`, in place of `emulator.cores`), and `emu-prepare` stamps them into the machine's device tree.

  Verify: the new testing/emulation test "Read core capacities" passes on both boards, and the network/transparent-proxy test "Enable CPU pinning" checks that dae runs on the board's big cores, fewer than all.

## 5. Device code without board facts (design D6)

- [x] 5.1 `files/etc/uci-defaults/91-wrt-datapath` sets PPPoE on the WAN interface and leaves its device to upstream's board script.

  Verify: the network/wan test "Image contains no credentials" checks PPPoE on the board's WAN port from the description, and "Dial after pushing credentials" passes on both boards (`eth1` on the R6S).
- [x] 5.2 dae's init pins to the CPUs of highest `cpu_capacity`, or to all CPUs without capacities, and its uci comment says so.

  Verify: the network/transparent-proxy test "Enable CPU pinning" expects exactly the highest-capacity CPUs the router reports, and passes on both boards.
- [x] 5.3 Replace "SD card" with "boot disk" in the comments and docs of wrt-data, containers and monitoring, and make the monitoring test's thermal check board-neutral.

  Verify: the services/monitoring, services/containers and storage/data-disk tests pass on both boards.
- [ ] 5.4 Keep qosify configured and on pppoe-wan however slowly the router comes up or redials: its init script configures the daemon whenever it comes up, waiting for as long as procd runs it (`patches/openwrt/0006`), and the daemon sets an interface up anew on a device replaced under the same name, as pppoe-wan is when a PPP session ends and another starts before the hotplug events are handled (`patches/openwrt/0010`).

  Verify: with every CPU of the VM kept busy, restarts and redials leave einat and qosify on pppoe-wan round after round, and the network/tc-hook-order test "After restarting components" passes in CI on both boards.

## 6. CI, signing and releases per board (design D9, D10)

- [x] 6.1 In `.github/workflows/build.yml`:
  - the host-toolchain job outputs the board list;
  - the firmware and system-test jobs run matrices over it, with per-board compiler-cache keys and `firmware-unsigned-<board>` artifacts;
  - update `docs/ci.md`.

  Verify: actionlint passes. `tests/build/test_boards.py` covers "Every board goes through the pipeline" from the workflow definition.
- [x] 6.2 The sign job signs every board's build into `signed/<board>`, in one job with one run step.

  Verify: the release/signing tests pass, including the workflow audits and "Artifact does not match the manifest" for a board's build.
- [x] 6.3 Add a `drill` matrix per board, with `drill-base <board>` taking its board's factory image, and an aggregate `upgrade-drill` job that fails unless the system tests passed and every drill succeeded, or signing did not run and so skipped every drill. `publish` needs the drills and the aggregate.

  Verify: the release/publishing test "Upgrade drill fails" checks the aggregate's conditions from the workflow, and `just github-audit` still passes against the ruleset.
- [x] 6.4 `scripts/release-publish.sh` takes every board's signed build:
  - it checks each set against its manifest, and all manifests against each other (lock, patches, upstream commit);
  - it prefixes `repo.tar` and the manifest files with the device;
  - it writes one `SHA256SUMS`, and `release.json` lists the boards.

  Verify: the release/publishing tests pass, including the new "Boards built from different sources".
- [x] 6.5 `wrt-sync`'s fetch takes only the assets of the device derived from `board_name`.

  Verify: the new release/device-sync test "Release with several boards" (a release carrying this build under two device names) passes. The existing device-sync tests pass on both boards, and a description test checks that `board_name` with `,` replaced by `_` equals `device` for every board.
- [x] 6.6 Update `docs/release-flow.md` (per-board asset sets, drills and the aggregate check) and `docs/ops.md` where it names the R4S.

  Verify: the pages match the workflow.
- [x] 6.7 Read the release manifest on the device with one ucode helper, `/usr/libexec/wrt-sync/manifest`: fetch takes the upgrade image's name from it, and wrt-sync the checksums of the image and the indexes. The helper fails unless the manifest lists one upgrade image and an index. wrt-sync checks the files in its own shell rather than at the end of a pipe, so neither an unreadable manifest nor a failed check can go unnoticed. The package depends on `ucode-mod-fs`.

  Verify: the new release/device-sync test "File that does not match the manifest" passes on both boards: a release whose upgrade image differs from its signed manifest is refused, and the previous release stays current.
- [x] 6.8 `drill-base` takes the factory image that the board's manifest in the latest stable release names, and checks it against the manifest. A board that no stable release carries yet starts from the candidate's own image. Any failure to look the release up, other than GitHub's answer that there is none, fails.

  Verify: the release/upstream-bump tests "Drill base of each board" and "Drill base cannot be had" pass against a stand-in `gh`.
- [x] 6.9 Tie each set to its board. `release-publish` refuses a release that lacks a board of `boards/`; `--boards` names a subset for the tests, which hold one board's build. The manifest records the board's device: `release-publish` checks it, and the manifest helper on the device requires it to be the router's.

  Verify: on both boards, the release/publishing test "A board missing" passes, and so does the release/device-sync test "Another board's manifest". The build/ci test "Complete manifest" checks the device.
- [x] 6.10 Keep the emulator responsive and the harness patient, on the slow work disk:
  - the emulator's and the tests' files go to `$WRT_TESTDIR`, on a disk that flushes fast (by default the work directory), and the work volume's loop device uses direct I/O;
  - the release tests derive variants of the signed build and of the release as linked copies (`wrt_tests.trees`), and `release-publish` links images into a release;
  - the router harness reopens an SSH connection the stalled emulator dropped, and retries a refused copy;
  - `Online.dial` waits until the LAN clients renewed their leases, and spaces the renewals;
  - the NAT tests send an unasked datagram again each second while the client listens, so that one lost on the emulated path fails no test (a datagram the NAT lets in or keeps out, it lets in or keeps out every time).

  Verify: the release suites and `network/test_nat.py` pass on both boards.
- [ ] 6.11 Keep the Actions caches within the 10 GB quota: a `caches` job after the firmware jobs keeps, of its ref's caches, the current toolchain and the newest download cache and compiler cache of each board. Each board's compiler cache holds what its build used (`WRT_CCACHE_TRIM`), and the firmware jobs restore the toolchain last, so that eviction takes a superseded cache before it.

  Verify: actionlint passes; after a CI run the ref holds one such set, each board's compiler cache about one build's worth, and a re-run of a firmware job still restores its toolchain.
- [ ] 6.12 Keep buildbot mode's attended sysupgrade clients (owut, luci-app-attendedsysupgrade) out of the release build: they upgrade from OpenWrt's build servers, and attendedsysupgrade-common puts their CA key among the image's trust anchors (`config/ci.seed`).

  Verify: the release/signing test "Check trust anchors in the image" passes in CI on both boards.

## 7. Board-neutral texts

- [x] 7.1 Make the texts outside the specs board-neutral:
  - the project context in `openspec/config.yaml`;
  - the `flake.nix` description, the workflow headers and the package descriptions;
  - comments that call the device "the R4S" where they mean any board. Comments citing earlier designs keep those designs' names.

  Verify: `tests/build/test_boards.py` covers "No board named outside its description": board devices, names and SoCs appear only under `boards/` and in `uboot/board-*`.
- [x] 7.2 Edit the Purpose texts of the main specs that name the R4S or the SD card directly, since deltas do not carry them: testing/emulation, testing/harness, firmware/toolchain, firmware/ab-layout, storage/data-disk.

  Verify: `openspec validate --specs` passes, and no Purpose names a single board.

## 8. Integration

- [x] 8.1 On the local VM, with room for the second board's build directories (`docs/dev-setup.md`): build both boards, and run the full suite in the emulator for each (`just test r4s dev`, `just test r6s dev`).

  Verify: all tests pass on both boards, and `spec-coverage --change board-model` reports no uncovered scenario.
- [ ] 8.2 Get a green CI run: firmware and system tests for both boards, and drills where signing is enabled.

  Verify: record the run and its timings per board in `docs/ci.md`.
