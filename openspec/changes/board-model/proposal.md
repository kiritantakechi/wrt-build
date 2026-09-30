# Proposal

## Why

Every layer of the project is written for exactly one board, the NanoPi R4S: the configuration selects it, two upstream patches name it, and the bootloader glue, the CPU tuning, the emulator, the tests and several specs spell out its SoC, boot disk and ports. The NanoPi R6S (RK3588S with four Cortex-A76 and four Cortex-A55 cores, 8 GB, a 32 GB eMMC, two 2.5 GbE ports and one 1 GbE port) is already supported upstream, in the same `rockchip/armv8` target and on the same kernel. Supporting it is therefore mostly a matter of turning the R4S-specific layer into a board model: each board becomes a description that the build, the bootloader glue, the emulator, the tests, CI and the releases read, rather than code that names it.

## What Changes

- **Board descriptions**: `boards/r4s.json` and `boards/r6s.json` declare every board fact once:
  - the OpenWrt device and board name, the SoC and the CPU tuning;
  - the U-Boot variant and environment directory;
  - the boot disk (SD card or eMMC), the ports and their roles;
  - the emulator's CPU model, cores, memory, boot disk kind and NICs.

  Everything else reads them. Nothing outside the descriptions and the U-Boot fragments names a board.
- **NanoPi R6S**:
  - A/B factory and upgrade images on its eMMC;
  - its U-Boot with the slot logic, the environment on the eMMC and the DesignWare watchdog started;
  - packages tuned with `-mcpu=cortex-a76.cortex-a55+crypto`;
  - emulated as an R6S: Cortex-A76, eight cores, 8 GB, an eMMC and three ports.
- **One build per board, from one tree** (**BREAKING** for local use):
  - the recipes take the board: `just config|build|test <board> <profile>`;
  - each board builds in its own build and output directories (OpenWrt's `CONFIG_BUILD_SUFFIX` and `CONFIG_BINARY_FOLDER`);
  - one board-neutral cross toolchain, which carries no board's CPU flags, serves every board;
  - outputs go to `out/<board>/<profile>`, and the manifest records the board.
- **Upstream patches reduced to generic hooks**:
  - the U-Boot patch applies the slot logic to every variant in a board table generated from the descriptions, instead of naming the R4S;
  - the image patch gives the A/B images to every device in that table;
  - the uboot-envtools patch is dropped: wrt-ab configures the environment location of any A/B system itself;
  - the move_config patch reads the boot partition's number from sysfs instead of parsing an MBR `PARTUUID`. This removes the wrong-partition case on GPT disks and the shell arithmetic error it could raise in preinit.
- **Board-neutral device code**:
  - the WAN stays on the port upstream's board scripts assign (the R6S's WAN is `eth1`) instead of a fixed `eth0`;
  - dae's optional CPU pinning targets the highest-capacity cores instead of `cpu4-5`.
- **CI and releases per board**:
  - a board matrix for the firmware and system-test jobs;
  - one sign job for every board's build;
  - an upgrade drill per board;
  - one release per pipeline run, carrying each board's asset set, published only when every board's drill passed.

  **BREAKING** for release assets: each board's set is prefixed by its OpenWrt device name, and `wrt-sync` fetches only its own board's set. No release has been published yet.
- **Tests per board**:
  - the emulated board is the board of the build under test;
  - board-specific checks read the board description;
  - a board with two LAN ports is tested across both.
- **Specs, docs and project context** describe boards in general. The R4S Enterprise edition, which the patches covered but no build selected, drops out.

## Capabilities

### New Capabilities
- `build/boards`: board descriptions as the single source of board facts; one build per board from one tree, on one board-neutral toolchain; the supported boards (NanoPi R4S, NanoPi R6S).

### Modified Capabilities
- `build/ci`: the manifest records the board.
- `firmware/toolchain`: the CPU tuning comes from the board.
- `firmware/kernel`: the emulator's boot disk is an SD card or an eMMC; the port drivers are the board's (requirement renamed).
- `firmware/rootfs`: the factory image carries its board's complete boot chain (requirement renamed).
- `firmware/ab-layout`: the layout lives on the board's boot disk.
- `firmware/boot-rollback`: every board's bootloader shares the emulator's slot logic, and counting writes nothing to the boot disk.
- `testing/emulation`: the emulator boots each board's image with that board's identity, instruction set, boot disk and ports (requirement renamed); two LAN ports form one LAN.
- `network/wan`: PPPoE on the board's WAN port.
- `network/transparent-proxy`: CPU pinning on the board's big cores.
- `services/monitoring`, `services/containers`, `storage/data-disk`: the boot disk in place of the SD card.
- `release/publishing`: each release carries one asset set per board, all from the same commit, and is published after every board's drill.
- `release/device-sync`: a device syncs only its own board's assets.
- `release/upstream-bump`: the drill runs on every board.
- `release/signing`: the sign job signs every board's build.

## Impact

- **New**:
  - `boards/`;
  - `uboot/board-r6s.env` and `uboot/board-r6s.config`;
  - board loading in the scripts and in `wrt_tests`;
  - `tests/build/test_boards.py`.
- **Changed**:
  - `scripts/{config,build,test,toolchain-build,drill-base,release-sign,release-publish}.sh` and the `justfile`;
  - `config/{target,toolchain}.seed` and `uboot/wrt-ab.mk`;
  - patches 0003–0006 (0006 removed);
  - `feed/utils/wrt-ab`, `feed/utils/wrt-sync`, `feed/net/dae` and `files/etc/uci-defaults/91-wrt-datapath`;
  - `tests/wrt_tests/{emu,net}.py`, `tests/targets/`, and the board constants of the test modules;
  - `.github/workflows/build.yml`, the docs and `openspec/config.yaml`.
- **CI**: twice the firmware and system-test jobs, run in parallel, and a compiler cache per board. The toolchain cache stays one.
- **Local builds**: building both boards needs about 45 GB more in `$WRT_WORKDIR`, one board-specific `build_dir`.
- **Hardware**: no real R6S has been tested. Until the first flash, the emulator and static inspection of the boot chain stand in for it.
