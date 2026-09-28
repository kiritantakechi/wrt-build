# Proposal

## Why

Upstream rockchip sysupgrade overwrites the running root partition in place (see `target/linux/rockchip/armv8/base-files/lib/upgrade/platform.sh`). If the new image fails to boot, or power is lost halfway through the write, the only fix is to pull the SD card and reflash it.

This project tracks upstream main weekly, so a "new build won't boot" failure is more likely than on a stable release. The R4S can only boot from the SD card, so it needs to recover automatically to the last working system without anyone touching the hardware.

## What Changes

- **BREAKING (relative to the upstream layout): the partition layout changes**
  - The SD card uses MBR with four primary partitions: boot-A, root-A, boot-B, root-B.
  - Each root slot holds an EROFS image plus its own f2fs overlay.
  - The first install must flash the factory image; devices on the upstream layout cannot be upgraded in place.
- **Two kinds of images are produced**
  - Factory image: contains both slots.
  - Single-slot upgrade image: carries metadata that sysupgrade can verify.
- **Slot selection in U-Boot**
  - Enable `BOOTCOUNT_LIMIT` on U-Boot 2026.07 through `UBOOT_CUSTOMIZE_CONFIG`.
  - The environment lives in the gap before the SD card partitions. The R4S U-Boot defconfig already places it at `0x3F8000` with a size of 32 KiB, matching the upstream uboot-envtools settings for orangepi-r1-plus.
  - The slot selection logic is compiled into the U-Boot boot command and does not depend on a boot script shared by both slots.
  - Once bootcount exceeds `bootlimit`, `altbootcmd` switches to the other slot.
- **Hardware watchdog**
  - Enable the RK3399 dw_wdt; procd feeds it periodically.
  - A kernel hang turns into a reset and increments bootcount.
  - The kernel reboots automatically after a panic. The rockchip kernel config sets `PANIC_TIMEOUT` to 0, so without a fix the system hangs forever after a panic.
- **Strict health check**
  - A boot counts as successful when: the system reaches userspace, br-lan is up, dropbear and uhttpd are listening, and every registered component check passes (for example, the dae and einat BPF programs are attached).
  - WAN is not checked, to avoid a false rollback when the ISP connection is down.
  - Once the checks pass, `fw_setenv` resets bootcount to zero and confirms the current slot as good.
- **sysupgrade flow**
  - Writes only the inactive slot.
  - The config backup goes into the target slot's boot partition and is migrated on first boot by `79_move_config`, changed to look it up per slot.
  - The new slot becomes the default only after it passes the health check.
- **uboot-envtools**: add the R4S environment location so Linux can read and write it.
- **Verify the whole A/B chain in the emulator**
  - Build a second `qemu_arm64` variant from the same U-Boot source, using the same slot selection logic and swapping only the board constants (MMC index, serial console, device tree source).
  - The emulator attaches the SD card through `sdhci-pci`, uses the factory image unmodified as the SD card, and keeps the environment at `0x3F8000` as well.
  - The spec scenarios for slot selection, counting, rollback, upgrade, power loss, and health check all become automated tests in `just test`.
  - The emulator now boots the factory image through this U-Boot, so every emulation test runs the real boot chain from U-Boot onward.
  - What only the RK3399 runs is checked statically in the build outputs: the shipped U-Boot carries the same slot logic as the emulated one, and the U-Boot and kernel configurations arm the DesignWare watchdog.

## Capabilities

### New Capabilities

- `firmware/ab-layout`: the A/B partition layout, plus the two image formats (factory image and single-slot upgrade image).
- `firmware/boot-rollback`: U-Boot slot selection, bootcount, the watchdog, and automatic rollback.
- `firmware/health-check`: the criteria for a successful boot, how checks are registered, and confirming the current slot.
- `firmware/ab-upgrade`: the sysupgrade flow that writes the inactive slot, and config migration.

### Modified Capabilities

- `firmware/rootfs`: the boot chain requirement moves from a boot script to the slot logic in U-Boot, with a kernel FIT in each slot.
- `testing/emulation`: the emulator boots the factory image through `uboot-wrt-qemu` instead of passing the kernel and its command line to QEMU.
- `firmware/kernel`: the emulator's disk becomes an SD card on sdhci-pci, which replaces virtio-blk among the emulation drivers.

## Impact

- **Upstream files to modify**:
  - the rockchip image recipes (`target/linux/rockchip/image/Makefile`, `armv8.mk`) and boot script;
  - `package/boot/uboot-rockchip/Makefile`;
  - `platform.sh` and `79_move_config` in base-files;
  - the rockchip config in uboot-envtools.
- **New in-house content**:
  - shared logic and two sets of board constants under `uboot/`;
  - `uboot-wrt-qemu` (a test artifact only), `wrt-slot`, and `wrt-healthcheck` in the in-house feed;
  - one `MMC_SDHCI_PCI` entry added to the virt driver group in `config/kernel.config`;
  - four test modules under `tests/firmware/`, one per spec.
- **Dependencies**: `r4s-build-foundation`, including the EROFS root filesystem, the patch workflow, the test framework, and the emulation environment. The datapath checks in the health check are registered by `r4s-ebpf-datapath`.
- **U-Boot is outside the A/B scope**: U-Boot is shared by both slots, and the single-slot upgrade image does not rewrite it. Updating U-Boot is a separate, infrequent operation and remains a single point of risk.
- **Device workload**: none. Every scenario runs in the emulator in CI or is checked statically in the build outputs.
