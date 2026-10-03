# Design

## Context

For motivation, see proposal.md. This design rests on the following, checked against the pinned upstream (OpenWrt `1019293`, U-Boot 2026.07) and the project as it stands.

**Upstream already supports the R6S in the R4S's target:**
- `rockchip/armv8` has `Device/friendlyarm_nanopi-r6s` (SoC `rk3588s`), and uboot-rockchip has the `nanopi-r6s-rk3588s` variant. TF-A for RK3588 is built from source; the DDR initialization is rkbin's binary blob.
- Upstream's board scripts make `eth1` the R6S's WAN, and `eth0` plus `eth2` its LAN.
- The armv8 kernel configuration already builds in what the RK3588 needs: DesignWare PCIe, the combo PHY, the eMMC controller, thermal and the DesignWare watchdog. Our kernel overlay adds only the emulator's drivers, so one kernel configuration serves both boards.

**The R6S's U-Boot:**
- its defconfig keeps the environment nowhere;
- its device tree numbers the SD card `mmc0` and the eMMC `mmc1`;
- the console is UART2 at `0xfeb50000`, 1500000 baud;
- its board directory is `board/friendlyelec/nanopi-r6s-rk3588s`;
- the RK3588's watchdog node is enabled.

**OpenWrt's directories:**
- The build and staging directories are named after architecture, CPU type and libc (`target-aarch64_generic_musl`), not after `CONFIG_EXTRA_OPTIMIZATION`.
- `CONFIG_BUILD_SUFFIX` appends a suffix to both. The toolchain directory takes no suffix. `CONFIG_BINARY_FOLDER` moves `bin/`.
- musl is compiled with `TARGET_CFLAGS`, which include `CONFIG_EXTRA_OPTIMIZATION`. `scripts/toolchain-build.sh` builds the toolchain from whatever configuration is active, today one with the R4S's `-mcpu`.

**The R4S is named in:**
- `config/target.seed` and `config/toolchain.seed`;
- patches 0003, 0004 and 0006, and `uboot/board-r4s.*`;
- `tests/wrt_tests/emu.py` and `tests/targets/emulation.yaml`, and the constants of about ten test modules;
- `files/etc/uci-defaults/91-wrt-datapath` (WAN on `eth0`) and dae's init (`taskset -c 4,5`);
- `scripts/build.sh`, whose globs such as `build_dir/target-*/u-boot-…` assume a single build.

**QEMU 11.1.1 (pinned)** has an `emmc` device for the SD bus, and the `cortex-a76` and `cortex-a55` models.

## Goals / Non-Goals

**Goals:**
- Adding a `rockchip/armv8` board that upstream supports means adding its description and its U-Boot fragments, and nothing else.
- Both boards are built, tested, drilled and published on every run, with the same checks, and no build can pick up another board's objects.

**Non-Goals:**
- Boards of other targets or subtargets, which need their own image and bootloader hooks.
- The R4S Enterprise edition and the R6C, although both are one description away.
- `-O3` and the patch audit (`toolchain-o3`), ucode and legacy removal (`device-modernization`), typer and tach (`python-tooling`). The only exception is pydantic for the board model (D1).
- Testing on a real R6S: none is available.

## Decisions

### D1. Board descriptions: `boards/<id>.json`, validated by one model

```
boards/r4s.json, boards/r6s.json   (ids: the file names, r4s and r6s)
  model         "FriendlyElec NanoPi R6S"         the device tree's model
  device        "friendlyarm_nanopi-r6s"          OpenWrt device (image names, release assets)
  board_name    "friendlyarm,nanopi-r6s"          /tmp/sysinfo/board_name, FIT compatible
  soc           { compatible: "rockchip,rk3588s",
                  loader: { signature: "RKNS", offset: 0 },    where the loader shows its SoC
                  cores: [530, 530, 530, 530, 1024, 1024, 1024, 1024] }
                                                  each core's capacity-dmips-mhz
  cpu           "cortex-a76.cortex-a55+crypto"    -mcpu of the board's packages
  uboot         { variant: "nanopi-r6s-rk3588s",
                  env_dir: "board/friendlyelec/nanopi-r6s-rk3588s" }
  boot_disk     "emmc"                            or "sd"
  ports         [ {device: eth0, role: lan}, {device: eth1, role: wan}, {device: eth2, role: lan} ]
  drivers       { platform: ["rk_gmac-dwmac", "rockchip-dw-pcie"], pci: ["r8169"] }
  dt_enabled    [ "/ethernet@fe1c0000", "/pcie@fe180000", "/pcie@fe190000" ]
  emulator      { cpu: "cortex-a76", memory: "8G" }
```

**The loader's signature:** `dumpimage` names the RK3399's loader (header v1: "RK33" in the SPL tag, at offset 2048), but prints no name for the RK3588's (header v2: the magic "RKNS" at offset 0), only verifying it. The description therefore gives the signature and its offset, and the boot-chain test checks both the signature and `dumpimage`'s verification.

**Why JSON:** the same file serves every reader without a new parser:
- POSIX sh scripts read it with `jq`, which the flake already provides;
- Python reads it natively;
- GitHub Actions takes the board list through `fromJSON`.

TOML would need a parser in the shell scripts. YAML has no `jq`.

**Validation:** a pydantic model, `wrt_tests.boards.Board`, is the schema. It is strict: unknown fields are rejected and types are checked. `just check` gains a `boards` check that loads every description with it. A second schema file (JSON Schema plus a validator) would say the same thing twice. This is the one place where this change takes a dependency the `python-tooling` change otherwise brings.

**Where facts live:**
- The U-Boot facts written in U-Boot's own syntax stay in `uboot/board-<id>.{env,config}`: the boot disk's MMC number, the console arguments, the kernel start command, the environment location and the watchdog. The description names their board by its id.
- The emulator's boot disk kind and size follow from `boot_disk`: an SD card is 4 GiB, an eMMC 32 GiB.

### D2. One tree, one toolchain, a build directory per board

```
            toolchain-build (board-neutral config)          just build <board> <profile>
                     |                                                |
   staging_dir/toolchain-aarch64_generic_gcc-15_musl   <- shared --+  board seed (generated):
   (+ wrt-toolchain.json: its flags, its C library's hash)          |    DEVICE_<device>=y
                                                                   |    EXTRA_OPTIMIZATION += -mcpu=<cpu>
   build_dir/target-aarch64_generic_musl_r4s   staging_dir/..._r4s |    BUILD_SUFFIX=<id>
   build_dir/target-aarch64_generic_musl_r6s   staging_dir/..._r6s |    BINARY_FOLDER=$TREE/bin/<id>
   bin/r4s/..., bin/r6s/...  -->  out/r4s/<profile>, out/r6s/<profile>
```

**Configuration:** `scripts/config.sh <board> <profile>` composes the profile's seeds, then a board seed generated from the description. `config/target.seed` keeps only the target and subtarget. `config/toolchain.seed` keeps only the board-neutral flags. The recipes become `just config|build|test <board> [profile]` and `just drill-base <board>`. `just boards` prints the board ids as JSON, for CI; given boards, it checks them first, and `just build` checks its board this way before any other step. An unknown board fails before anything is configured, naming the known ones.

**Toolchain:**
- `toolchain-build` configures the tree for every board's device at once and for none of their CPU tuning, so musl, libgcc and libstdc++ carry no board's `-mcpu`, and the host tools are the ones every board's build needs. The devices are named explicitly: the ci profile's buildbot mode would otherwise enable every device of the target. It records `TARGET_CFLAGS` and the hash of the C library in `wrt-toolchain.json` in the toolchain directory, which travels in the cached archive. A toolchain without that record, or whose C library is not the one it names, is built anew: a board's build may have rebuilt musl with the board's flags, and recording that C library again would hide it.
- `build.sh` refuses a toolchain which has no record, whose recorded flags hold a board's `-mcpu`, or whose C library is not the one the record names. It checks the C library again after the build: OpenWrt builds musl with the target's flags, so a board's build that rebuilt the toolchain would leave the board's `-mcpu` in it.
- A local `just build` runs `toolchain-build` first, which builds nothing when the toolchain is current, so the first board built can never shape the toolchain.
- `toolchain-build` also writes the toolchain's version stamp (`stamp/.ver_check`) as buildbot mode would. In the release profile's buildbot mode, every make in the tree deletes a toolchain whose stamp does not name the last commit of `toolchain/`, and the board's build and staging directories with it. A toolchain built for the dev profile has no stamp, so without this a local switch to the ci profile would wipe it.
- That check itself raced under a parallel build, and wiped the toolchain of a CI build whose stamp was right: a stamp naming the right version is never touched, so once a make from the top level has touched `tmp/.build`, every make that reads the top-level Makefile checks it again, and world's sub-makes did so at once, each writing the version to the same `tmp/.ver_check` before comparing it. One truncating the file while another compared it made the other delete the toolchain and restart without a compiler. `patches/openwrt/0009` keeps the version in a shell variable instead, so concurrent checks share no file.
- The toolchain cache key covers the board-neutral configuration the toolchain is built from, as `compose_seeds` writes it: every seed of the profile and every board's device, and none of the boards' other facts.

**Outputs:** `build.sh` finds its board's U-Boot and kernel build directories through `BUILD_SUFFIX`, not through globs. It copies `bin/<id>` into `out/<board>/<profile>`, and writes `board` into the manifest.

**Alternatives:**
- A source tree per board: it doubles the host tools and the toolchain, locally and in the caches.
- Subtargets per SoC patched into upstream: a large, permanent divergence.
- Cleaning `build_dir` when switching boards: a full rebuild each time.

**Trade-off:** the C library and the C++ runtime in the images are tuned for the generic ARMv8.0 baseline, not per board (Risks).

### D3. Bootloader: per-board fragments and a generic hook

`uboot/board-r6s.env` sets:
- `wrt_mmc=1`, the eMMC;
- `wrt_console=console=ttyS2,1500000 earlycon=uart8250,mmio32,0xfeb50000`;
- `wrt_bootos=bootm ${kernel_addr_r}`.

`uboot/board-r6s.config` places the environment on the eMMC (`ENV_MMC_DEVICE_INDEX=1`; U-Boot 2026.07 renamed `SYS_MMC_ENV_DEV`, and Rockchip's U-Boot uses the index only when it cannot tell the MMC device it booted from) and starts the DesignWare watchdog with a 60-second timeout, as `board-r4s.config` does. The environment location (offset `0x3F8000`, 32 KiB) is one project constant, in `wrt-ab.config`. The R4S's defconfig already has it, and every board and the device side share it.

**Patch 0003** shrinks to one generic line in uboot-rockchip's Makefile: the include of `env/uboot/wrt-ab.mk`, after the variants' definitions and before the package is built. The hook itself lives in `wrt-ab.mk` and is evaluated for `$(BUILD_VARIANT)`: a board's variant gets `wrt-ab board-<id>` appended to its `UBOOT_CONFIG`, on a line of its own after its definition's last. The scripts that prepare the tree (`fetch`, `toolchain-build` and `config`) generate the board table `env/wrt-boards.mk` from the descriptions: each board's variant, id and environment directory, and each board's device. It sits beside the `env/uboot` link to `uboot/`, never in the repository. `wrt-ab.mk` looks the building variant up in it. A known variant gets the fragments, the writeable-list flags and the `Build/Prepare` step. Any other variant is untouched. No board is named in the patch.

**`uboot-wrt-qemu`** stays one package with `board-qemu`, which every board's emulator boots.

### D4. Images and the environment tool without board names

**Patch 0004** keeps `gen_image_ab.sh`, `ab-boot`, `ab-disk` and `Device/wrt-ab`. Instead of adding `$(Device/wrt-ab)` to device definitions, `Device/Default` applies it to the devices in `WRT_AB_DEVICES`, which comes from `env/wrt-boards.mk`. Neither board's upstream definition sets `IMAGES`, so the A/B images stand.

**Patch 0006 is dropped.** wrt-ab installs a uci-defaults script that runs after uboot-envtools' own. It writes `/etc/config/ubootenv` for the boot disk (`export_bootdevice`) at the shared offset whenever the system booted from a slot, meaning `wrt.slot` is on the command line. This works for any A/B board and is our own package, not an upstream patch.

### D5. move_config reads the partition number from sysfs (patch 0005)

It resolves the root partition's block device from the command line's `PARTUUID` through sysfs uevents, as `export_bootdevice` does, and reads that device's `partition` attribute. The boot partition is the one before it.

This handles MBR and GPT disks, and a `root=/dev/...` command line. It never runs arithmetic on text parsed from a UUID: the old `$((0x${suffix} - 1))` aborts busybox ash in preinit on a non-hex suffix, and picks a wrong partition on a GPT UUID.

### D6. Device code without board facts

- **`91-wrt-datapath`** sets the WAN's protocol to PPPoE and leaves its device as upstream's board script created it: `eth0` on the R4S, `eth1` on the R6S.
- **dae's init** pins to the CPUs whose `/sys/devices/system/cpu/cpu*/cpu_capacity` is highest, which are the big cores on both SoCs. Without capacities, where all cores are equal, it uses all CPUs. The rule needs no board data. The emulator can check it because it gives each core its capacity from the description (D7).

Alternative: bake the big-core list into each board's image from the description. That needs a per-board file in the shared rootfs overlay, for a fact the kernel already knows.

### D7. The emulator follows the description

**`emu-prepare`** writes the labgrid target description into the emulator directory, from the build's board. It stops being a checked-in `emulation.yaml`. The machine gets:
- the description's CPU and memory, and the SoC's cores, each with its capacity (`capacity-dmips-mhz`) stamped into the device tree, so the kernel reports the big cores as on the board;
- the boot disk as `sd-card` or `emmc` on `sdhci-pci`;
- one `virtio-net-pci` per port, in the board's order, each on a tap named after its segment;
- the `i6300esb` watchdog and the xHCI controller.

The device tree QEMU generates is stamped with the board's name and model, as it is today for the R4S. The emulator directory is keyed by the image, the firmware and the board description. `emu-prepare` removes the directories of builds that have changed since, so that two boards' emulators fit beside their builds.

**The sandbox** (`wrt_tests.net`) takes the port list:
- the WAN port joins `br-wan`;
- the first LAN port joins `br-lan`, with the runner and `client-a`/`client-b`;
- a second LAN port joins a segment of its own, `br-lan2`, with `client-c`. The router bridges both LAN ports into one LAN, which the new emulation scenario checks.

### D8. Tests read the board of the build under test

The build manifest names the board, and a session fixture `board` loads its description. The constants that were the R4S's now come from it:
- the loader's signature, the device-tree nodes and compatibles;
- the port drivers, the CPU model and the board name.

Each scenario keeps one test. The one scenario a board cannot exercise, a second LAN port on the R4S, skips there.

**No board named in code:** `tests/build/test_boards.py` searches scripts, configuration, feed packages, patches and tests for every board's device, board name and SoC, and allows them only under `boards/` and in `uboot/board-*`. The FIT-parsing unit test's sample moves to a neutral board name.

### D9. CI: a board matrix, one sign job, one aggregate drill check

```
host-toolchain --(boards: ["r4s","r6s"])--> firmware (matrix board) --> system-test (matrix board x suite)
   --> sign (one job, every board, one approval) --> drill (matrix board)
   --> upgrade-drill (aggregate: all drills succeeded or were skipped) --> publish (all boards)
```

- **host-toolchain** outputs the board list (`just boards`).
- **firmware** and **system-test** run a matrix over it. Artifacts are named `firmware-unsigned-<board>`, and each board has its own compiler-cache key.
- **sign** stays one job: one approval, and one job that ever holds the keys. It signs each board's build into `signed/<board>`.
- **drill** runs per board.
- **upgrade-drill** is the required check the ruleset names. A matrix job would report as `drill (r4s)` and `drill (r6s)` instead. This aggregate job needs `system-test`, `sign` and `drill`, and runs `if: always()`. It fails unless the system tests passed and either every drill succeeded, or signing did not run at all and so skipped the drills (pull requests, or no release keys yet). A failed or rejected signing also skips the drills; that fails the check, since a skipped required check would otherwise let a bump merge undrilled. `github-audit` and the ruleset stay as they are.
- **publish** needs `drill` as well as `upgrade-drill`, so it runs only when every drill actually succeeded.

### D10. Releases: one release, one asset set per board

**`release-publish.sh`** takes every board's signed build:
- it refuses a release that lacks a board of `boards/`, so that no board's devices are left without their set. The tests, which have one board's build, name that board with `--boards`;
- it checks each board's set against its own manifest (run identifier), which names the board and its device;
- it checks that all manifests agree on the `upstream.lock` hash, the patch queue hash and the upstream commit;
- it names `repo.tar`, `manifest.json` and `manifest.json.sig` `<device>-…` (the images already carry the device name);
- one `SHA256SUMS` covers every asset, and `release.json` lists the boards.

**`wrt-sync`** derives its device from `board_name` by replacing `,` with `_`, which is upstream's naming for both boards. A test asserts it for every description. `fetch` takes only that device's assets, and each set is verified on its own.

Both read the manifest with one ucode helper, `/usr/libexec/wrt-sync/manifest`: `fetch` takes the upgrade image's name from it, and `wrt-sync` the checksums of the image and the indexes. The helper fails unless the manifest names the router's device and lists one upgrade image and an index. Every board's manifest is signed with the same key, and apk cannot tell the boards' packages apart (they share the package architecture), so only the manifest keeps a router from activating another board's set published under its name. `wrt-sync` checks the files in its own shell, not at the end of a pipe. The check this replaces read the manifest with a ucode call that could not run (`readfile` lives in the `fs` module), and its pipe hid the failure, so nothing was checked.

**`drill-base <board>`** takes its board's factory image from the latest stable release: the one the board's manifest there names, checked against it. While no stable release carries the board, before the first release or when the board is new, the drill starts from the candidate's own image. Only GitHub's answer that there is no release counts as none: any other failure to look it up fails the drill, which would otherwise upgrade the candidate onto itself.

### D11. Names and references

- Board ids are short: `r4s` and `r6s`.
- The U-Boot fragments keep the `board-<id>` naming they already have.
- Comments citing earlier designs (`r4s-ab-rollback D4` and so on) keep those designs' names, which is what they are archived under. New references cite `board-model`.
- `openspec/config.yaml` and the main specs' Purpose texts are made board-neutral. Purposes are edited directly when this change is archived, because deltas do not carry them.

## Risks / Trade-offs

- **[No R6S to test on]** The eMMC boot chain, the DDR blob and the real ports go unexercised until the first flash. → The emulator runs the R6S's own image with its identity, instruction set, eMMC and ports, and the boot chain is inspected statically. The upgrade image never carries U-Boot, so a bad bootloader can only come with a factory image. The docs describe maskrom recovery.
- **[Generic C library]** musl, libgcc and libstdc++ are not tuned per board. → Their hot paths are small next to the packages built with the board's flags. Per-board toolchains would double the 75-minute toolchain build and its cache.
- **[A toolchain built with board flags by accident]** → The recorded flags, the refusal in `build.sh`, and `toolchain-build` running first locally.
- **[Twice the CI work]** → The matrices run in parallel, so a run takes about as long as before. The GitHub cache gains one compiler cache of about 1.2 GB, within the 10 GB quota.
- **[Local disk]** A second board adds about 45 GB of `build_dir`. → Documented in `docs/dev-setup.md`. The shared tree, toolchain and downloads are not duplicated.
- **[`board_name` to device mapping]** → A test per description guards it. A future board where the rule fails gets an explicit `device` lookup on the device side, which is a change to that mapping only.
- **[An 8-core A76 guest under TCG]** It is slower, and some timeouts were tuned on the R4S. → The R6S suites run in CI from the start, and timeouts that fail are raised where the test waits, not globally.
- **[rkbin's DDR blob]** The R6S loader contains a binary. → It is upstream's choice for every RK3588 board, and `docs/supply-chain` records it.

## Migration Plan

1. **Local builds** name the board: `just build r4s dev` replaces `just build dev`, and outputs move from `out/dev` to `out/r4s/dev`. The old output directories can be deleted.
2. **Release assets** are prefixed from the first release on. No release has been published, so no device syncs the old names.
3. **R4S devices** keep their layout and bootloader. Fresh configurations get the same WAN device as before (`eth0`, now from upstream's board script).
4. **R6S first install:** write the factory image to the eMMC, from a system booted from an SD card or over USB in maskrom mode (`docs/migration-single-to-ab.md`).
5. **Rollback** reverts the change. Devices store nothing new, and release asset names are the only external format that changes.

## Open Questions

- The R6S loader's signature ("RKNS" at offset 0, from U-Boot's `rkcommon.c`), to be confirmed on the first build's factory image. It is data in the description.
- Whether 8 GB of emulator memory for the R6S is practical on the CI runners. The description can lower it without any spec or approach changing.
