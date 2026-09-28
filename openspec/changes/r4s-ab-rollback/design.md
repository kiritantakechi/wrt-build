# Design

## Context

See proposal.md for the motivation. All of the current state below was verified against upstream source (OpenWrt main `1019293`, U-Boot v2026.07):

- **Image generation**: `scripts/gen_image_generic.sh` supports only two partitions, "kernel + rootfs"; without a GUID, the boot partition is generated as ext4 by `make_ext4fs`.
- **Upgrade flow**: rockchip's `platform.sh` writes the entire disk image to the boot disk with `dd`; `79_move_config` always takes `sysupgrade.tgz` from partition 1.
- **U-Boot environment**: `configs/nanopi-r4s-rk3399_defconfig` already enables `ENV_IS_IN_MMC` with `ENV_OFFSET=0x3F8000`; when rockchip adds MMC, `ENV_SIZE` defaults to `0x8000`.
- **U-Boot capabilities**: `ENV_WRITEABLE_LIST` is supported; `BOOTCOUNT_ENV` counts and saves only when `upgrade_available` is 1; the R4S defconfig does not enable `WDT`, but `DESIGNWARE_WATCHDOG` defaults to y for RK3399.
- **Kernel watchdog**:
  - `DW_WATCHDOG=y`;
  - `WATCHDOG_HANDLE_BOOT_ENABLED=y`: when the watchdog is already running, the kernel feeds it until userspace takes over;
  - `WATCHDOG_OPEN_TIMEOUT=0`: the kernel feeds it on userspace's behalf indefinitely.
- **Kernel panic**: rockchip has `PANIC_TIMEOUT=0`, so the system hangs forever after a panic.
- **fstools**: the overlay starts at the end of EROFS, rounded up to a 64 KiB boundary.
- **Prerequisites from the foundation**: the emulation environment (testing/emulation), which runs the shipped image under the R4S board identity; and the `config/kernel.config` overlay mechanism.

## Goals / Non-Goals

**Goals:**
- An upgrade never touches the running slot; when the new system fails to boot, it recovers automatically without touching the hardware.
- The slot selection logic is fixed in the bootloader; the Linux side only reads and writes three variables.
- The health check is extensible, so later changes can register checks with it.
- This A/B state machine runs end to end in the emulator: same U-Boot version and logic, same SD card, partitions, and environment offset.

**Non-Goals:**
- A/B and online updates for U-Boot itself. U-Boot is updated only when the factory image is flashed.
- Verified boot (signed FIT, dm-verity). Rejected during exploration: the R4S SD card is removable, and the eFuses are not blown.
- Datapath checks; those are registered by `r4s-ebpf-datapath`.

## Decisions

### D1. Partition layout

```
offset        content                         size
0x8000        idbloader (TPL + SPL)           < 4 MiB
0x3F8000      U-Boot env                      32 KiB
0x800000      u-boot.itb (U-Boot + TF-A)      < 24 MiB
32 MiB        p1 boot-A   ext4                64 MiB   kernel.img (FIT), sysupgrade.tgz handoff
              p2 root-A                       1024 MiB [EROFS][64K align][f2fs overlay]
              p3 boot-B   ext4                64 MiB
              p4 root-B                       1024 MiB
total ~ 2.2 GiB  -> fits a 4 GB card
```

- **Use MBR**: consistent with upstream, and four primary partitions are exactly enough. GPT brings no extra benefit and would diverge from upstream.
- **64 MiB boot partitions**: enabling BTF and adding the virt platform drivers makes the kernel FIT larger; this leaves headroom.

### D2. Image artifacts

- **Generator script**: `scripts/gen_image_ab.sh` uses `ptgen` to create the four partitions; the boot partitions still use `make_ext4fs`.
- **Factory image**: both slots have identical contents, and the U-Boot environment area is zero-filled, so the first boot goes to slot A.
- **Upgrade image**: `sysupgrade.tar`, reusing `Build/sysupgrade-tar`. It contains `kernel` (the ext4 image of the boot partition), `root` (EROFS), and `CONTROL`, with metadata attached by `append-metadata`.
- **Alternative**: keep the whole-disk image and slice partitions out of it. Rejected, because the whole-disk image carries U-Boot and the partition table.

### D3. U-Boot: logic fixed in the binary, split into two layers, "shared logic + board constants"

```
uboot/wrt-ab.env          common state machine (single source of truth)
uboot/board-r4s.env       wrt_mmc=1  wrt_console=ttyS2,1500000
                          wrt_earlycon=uart8250,mmio32,0xff1a0000  wrt_fdt=      (FIT dtb)
uboot/board-qemu.env      wrt_mmc=0  wrt_console=ttyAMA0
                          wrt_earlycon=                            wrt_fdt=${fdtcontroladdr}
```

- **Two symmetric builds**: each U-Boot build concatenates "board constants + shared logic" into the text environment file that `ENV_SOURCE_FILE` expects.
  - The shipped `nanopi-r4s-rk3399` variant: modify `package/boot/uboot-rockchip/Makefile`, applying it through `UBOOT_CUSTOMIZE_CONFIG` to this variant only.
  - The test `qemu_arm64` build: lives in the `uboot-wrt-qemu` package in the in-house feed. It is a test artifact only and does not go into the firmware.
  - Both must match the `uboot-rockchip` version exactly, enforced by the code-standard checks.
- **Config shared by both builds**:

```
--enable BOOTCOUNT_LIMIT --enable BOOTCOUNT_ENV --set-val BOOTCOUNT_BOOTLIMIT 3
--enable ENV_WRITEABLE_LIST
--set-str ENV_FLAGS_LIST_STATIC "boot_slot:sw,bootcount:dw,upgrade_available:dw,<runtime vars>:sw"
--enable USE_BOOTCOMMAND --set-str BOOTCOMMAND "run wrt_boot"
r4s only:  --enable WDT --enable WATCHDOG_AUTOSTART --set-val WATCHDOG_TIMEOUT_MSECS 60000
qemu only: --disable ENV_IS_IN_FLASH --enable ENV_IS_IN_MMC --set-val SYS_MMC_ENV_DEV 0
           --set-hex ENV_OFFSET 0x3F8000 --set-hex ENV_SIZE 0x8000
           --enable MMC --enable DM_MMC --enable MMC_SDHCI --enable MMC_PCI   (sdhci over PCI)
```

- **Shared logic**:

```
wrt_boot:
  if boot_slot != b: boot_slot=a, bp=1, rp=2   else: bp=3, rp=4
  part uuid mmc ${wrt_mmc}:${rp} rootuuid
  load mmc ${wrt_mmc}:${bp} ${kernel_addr_r} kernel.img || run wrt_fallback
  bootargs = console=${wrt_console} [earlycon=${wrt_earlycon}] root=PARTUUID=${rootuuid}
             rw rootwait panic=5 watchdog.open_timeout=90 wrt.slot=${boot_slot}
             fstools_overlay_compression_type=zstd
  bootm ${kernel_addr_r} [- ${wrt_fdt}]

altbootcmd  (bootcount > bootlimit):
  boot_slot = other; upgrade_available=0; bootcount=0; saveenv; run wrt_boot

wrt_fallback (load failure, same power cycle):
  if wrt_tried unset: wrt_tried=1; boot_slot = other; run wrt_boot
  else: stop at U-Boot prompt (no loop)
```

- **Only three variables are opened up**: `ENV_WRITEABLE_LIST` ensures that only variables registered as writable are read from the persistent environment, so the logic always comes from the binary itself. Every temporary variable set with `setenv` during boot must also be registered as writable; the emulation tests cover each one, so there is no need to wait for a serial console check on the device.
- **Two panic-related parameters**: `panic=5` overrides rockchip's `PANIC_TIMEOUT=0`; `watchdog.open_timeout=90` limits how long the kernel feeds the watchdog on userspace's behalf.
- **Alternatives**:
  - Select the slot with a shared boot.scr. Rejected, because it is itself a single point of failure and can be overridden by the persistent environment.
  - Skip `ENV_WRITEABLE_LIST`. Rejected, because saved old logic would shadow newer logic later.

### D4. Reading and writing the environment from Linux

- **uboot-envtools**: patch in the R4S config; the boot disk is determined dynamically by `export_bootdevice`, with offset `0x3F8000` and size `0x8000`. The emulator uses the same config, because the SD card is an MMC device there too.
- **The `wrt-slot` command**:
  - `wrt-slot status` prints the current slot, `upgrade_available`, `bootcount`, and the result of the most recent health check.
  - `wrt-slot switch` writes the three variables with `fw_setenv -s`, then reboots.
- **Symmetric design**: `status` and `switch` map to "read" and "write"; there are no other subcommands.

### D5. Health check

`wrt-healthcheck` starts at `START=99`:

```
wait up to 300s, poll every 10s:
  builtin: ubus system ready; network.interface.lan up with IPv4;
           dropbear listening on LAN addr :22; uhttpd listening on LAN addr :80
  registered: /etc/healthcheck.d/*  (executable, exit 0 = pass, 30s timeout each)
result -> /var/run/wrt-healthcheck.json (time, pass/fail, failed items)
trial (upgrade_available=1): pass -> fw_setenv -s {bootcount 0, upgrade_available 0}
                             fail/timeout -> logger + reboot
confirmed: fail -> logger only
```

- **Why WAN is not checked**: an ISP outage does not mean the system is broken.
- **Why a confirmed system does not reboot on failure**: a confirmed system has no rollback target, so rebooting would only loop in place.

### D6. Upgrade flow

- **`platform_check_image`**: accepts only the single-slot upgrade tar, and checks the metadata.
- **`platform_do_upgrade`**:
  1. derive the target slot from `wrt.slot`;
  2. `dd` kernel and root to the target slot's two partitions;
  3. starting at the end of EROFS rounded up to 64 KiB, zero the next 1 MiB;
  4. run `fw_setenv -s` to write the three variables.
- **Config migration**: `platform_copy_config` writes the config backup to the target slot's boot partition; `79_move_config` uses `wrt.slot` to find the current slot's boot partition.

### D7. Verification: the A/B chain in the emulator

```
qemu-system-aarch64 -machine virt,gic-version=3 -cpu cortex-a72 -m 4G
  -bios u-boot.bin                         # uboot-wrt-qemu: same version + same wrt-ab.env
  -dtb r4s.dtb                             # R4S identity (foundation D14), also U-Boot's control DT
  -device sdhci-pci -device sd-card,drive=sd0 -drive if=none,id=sd0,file=factory-overlay.qcow2
  -netdev tap ... (foundation topology)  -device i6300esb -action watchdog=reset
```

- **What the emulator tests**: U-Boot and Linux both see an MMC device, the factory image is used unmodified as the SD card, and the environment is also at `0x3F8000`. The boot-rollback scenarios (slot selection, counting, rollback, switching slots within the same power cycle, stopping at the prompt when both slots fail, and the persistent environment being unable to override the boot logic) all go through the same `wrt-ab.env`.
- **ab-upgrade, health-check, ab-layout**: all of their scenarios run in the emulator using the shipped Linux-side code.
  - Power loss mid-write: throttle disk writes, then kill the QEMU process during `dd`.
  - Bad kernel: put a corrupted FIT in the upgrade tar.
  - WAN down: do not start the PPPoE server in the `isp` namespace.
- **Kernel addition**: the emulated SD card controller needs `CONFIG_MMC_SDHCI_PCI=y`, which this change adds to the virt driver group in `config/kernel.config`.
- **The emulator boots through U-Boot from now on**: `emu-prepare` no longer extracts the kernel or derives bootargs; QEMU gets `-bios u-boot.bin` and the factory image as the SD card, so every emulation test, including the foundation's, runs U-Boot's slot logic and the slot's own kernel FIT. `-dtb r4s.dtb` becomes U-Boot's control device tree, which `wrt_fdt` hands on to Linux.
- **Watchdog in the emulator**: procd opens the i6300esb and feeds it, as it feeds the DesignWare watchdog on the R4S. `ubus call system watchdog '{"stop": true}'` stops the feeding without closing the device, so the i6300esb resets the machine and U-Boot counts the boot. QEMU's U-Boot has no i6300esb driver, so the part before userspace (U-Boot starts the watchdog, the kernel feeds it until userspace opens it) is checked statically, below.
- **Checked statically, in the build outputs** (what only the RK3399 runs; no step needs the device):
  1. **Same logic**: the test reads the built-in environment of the shipped U-Boot (inside `u-boot.itb`) and of `uboot-wrt-qemu`, and requires them to be identical apart from the four board constants of D3. The R4S U-Boot's control device tree must alias `mmc1` to the SD card controller (`mmc@fe320000`), matching `wrt_mmc=1`.
  2. **Watchdog chain**: the R4S U-Boot `.config` has `WDT`, `WATCHDOG_AUTOSTART` and `WATCHDOG_TIMEOUT_MSECS=60000`; the kernel `.config` has `DW_WATCHDOG=y` and `WATCHDOG_HANDLE_BOOT_ENABLED=y`; the built-in environment passes `watchdog.open_timeout=90`. `scripts/build.sh` copies both `.config` files into the outputs as `kernel.config` and `u-boot.config`, listed in `manifest.json`, so `system-test` reads them from the artifact.
  3. **Boot chain**: the foundation's boot chain test, updated for the factory image (firmware/rootfs, modified here): the loader, the U-Boot FIT, and a kernel FIT with the R4S device tree in each slot.

## Risks / Trade-offs

- **[`ENV_WRITEABLE_LIST` misses a runtime variable]** The emulation tests cover every boot path, so an unregistered variable shows up in CI.
- **[The emulated U-Boot diverges from the shipped U-Boot]** There is only one copy of the shared logic; the code-standard checks compare the U-Boot versions of the two packages; the board constants may contain only the variables listed in D3.
- **[There is only one U-Boot]** It is updated only when the factory image is flashed; U-Boot version changes do not reach devices with each weekly bump.
- **[A health check that is too strict causes false rollbacks]** 300 seconds total, 30 seconds per check, and only LAN-side and local state are checked.
- **[fstools misreads leftover overlay data]** The upgrade zeroes the 1 MiB after EROFS.
- **[SD card index on the device]** `wrt_mmc=1`, following the `mmc1` alias of the R4S device tree; the static check in D7 ties the constant to the alias.
- **[The part before userspace never runs before release]** The emulator cannot start a watchdog from U-Boot, so an early kernel hang is only covered by the configuration checks in D7. A panic and a userspace hang both run in the emulator, and both count toward rollback.

## Migration Plan

1. On the single-slot system, run `sysupgrade -b` to export a config backup.
2. On a computer, write the A/B factory image to the SD card (this is the BREAKING change).
3. After boot, restore the backup from step 1.
4. Use single-slot upgrade images for all later upgrades. To roll back, use `wrt-slot switch` or wait for the automatic rollback.

## Open Questions

- Both root partitions use 1024 MiB. They can be enlarged for a bigger SD card without affecting the specs.
