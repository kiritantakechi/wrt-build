# Tasks

## 1. Bootloader (shared logic + two board builds)

- [x] 1.1 Write `uboot/wrt-ab.env` and `uboot/wrt-ab.config` (the shared logic and configuration), the symmetric `uboot/board-r4s.{env,config}` and `uboot/board-qemu.{env,config}` (only the three constants of design D3 and each board's options), and the build glue `uboot/wrt-ab.mk`, which also passes the writable list. Verification: "Compare the two bootloaders" confirms that the two board files define the same three names and that both built environments carry the same shared logic.
- [x] 1.2 Modify `package/boot/uboot-rockchip/Makefile` so the change applies only to the `nanopi-r4s-rk3399` variant: concatenate the environment file, and append the shared config and the r4s-specific config. Verification: the static tests in 5.1 read these options from the shipped `u-boot.config`; the `.config` of every other rockchip variant is unchanged.
- [x] 1.3 Add the `uboot-wrt-qemu` package to the in-house feed: build `qemu_arm64` from the same U-Boot source package through `wrt-ab.mk`, taking `PKG_VERSION` and `PKG_HASH` from `uboot-rockchip/Makefile`; it installs nothing. Verification: the emulator boots the factory image through it (4.1).
- [x] 1.4 Add `CONFIG_MMC_SDHCI_PCI=y` to the virt driver group in `config/kernel.config`, and fill in the sub-options with `listnewconfig`. Verification: the kernel config check passes after the build.
- [x] 1.5 Make `scripts/build.sh` copy the final kernel `.config`, both U-Boot `.config` files and the `uboot-wrt-qemu` binary into the outputs (`kernel.config`, `u-boot-r4s.config`, `u-boot-qemu.config`, `u-boot-qemu.bin`), each listed in `manifest.json`. Verification: the `firmware-unsigned` artifact carries all of them, and `system-test` reads them from it.

## 2. Images

- [x] 2.1 Implement `scripts/gen_image_ab.sh`, and add a factory image rule to the rockchip image recipe (four partitions, zero-filled environment area). Verification: `tests/firmware/test_ab_layout.py` checks the order and sizes in the partition table and confirms the total size is within 4 GB.
- [x] 2.2 Add a rule that builds the single-slot upgrade tar, with metadata attached. Verification: `test_ab_layout.py` checks that the tar contains only kernel, root, and CONTROL, and that the metadata names the correct board.

## 3. Linux side

- [x] 3.1 Modify uboot-envtools to add the R4S config. Verification: in the emulator, `fw_printenv boot_slot` reads a value; after `fw_setenv`, `printenv` shows the change after rebooting into U-Boot.
- [x] 3.2 Implement the `status` and `switch` subcommands of `wrt-slot` in the `wrt-ab` package of the in-house feed. Verification: covered by the manual slot switch test in `test_boot_rollback.py`.
- [x] 3.3 Implement `wrt-healthcheck`: built-in checks, the `/etc/healthcheck.d/` registration mechanism, per-check and total time limits, the JSON result, and handling for both the trial boot and confirmed states. Verification: `test_health_check.py` covers every scenario in the health-check spec.
- [x] 3.4 Implement `platform_check_image`, `platform_do_upgrade` and `platform_copy_config` for A/B in `/lib/upgrade/wrt-ab.sh` of the `wrt-ab` package, which replace those of the rockchip `platform.sh` (design D6), and patch `79_move_config` to take the boot partition before the root partition. Verification: `test_ab_upgrade.py` covers every scenario in the ab-upgrade spec.

## 4. Emulator tests (all run in `just test`)

- [x] 4.1 Switch the emulation environment to the bootloader chain: load `uboot-wrt-qemu` with `-bios`, attach the factory image as the SD card through `sdhci-pci`, drop the kernel extraction and bootargs derivation from `emu-prepare`, and allow disk writes to be throttled (for power-loss tests). Verification: the emulator self-tests (testing/emulation, as modified here) cover provenance, boot, power loss and reboot; the whole foundation suite passes on the factory image.
- [x] 4.2 Write `tests/firmware/test_ab_layout.py`, covering every scenario in the ab-layout spec (the 4 GB scenario is judged by image size). Verification: all tests pass.
- [x] 4.3 Write `tests/firmware/test_boot_rollback.py`, covering these scenarios: slot selection for a, b, and an invalid value; the persistent environment cannot override boot logic; rollback after three failed trial boots; no counting during normal operation; switching slots within the same power cycle on a load failure; stopping at the prompt when both slots fail; reboot and count within 10 seconds after a kernel panic; reset and count when procd stops feeding the watchdog during a trial boot. Verification: all tests pass.
- [x] 4.4 Write `tests/firmware/test_health_check.py`: passes with WAN down, fails when uhttpd is not listening, a registered check fails or times out, handling for the trial boot and confirmed states, and the status query. Verification: all tests pass.
- [x] 4.5 Write `tests/firmware/test_ab_upgrade.py`: writes only the inactive slot (checksums unchanged), power loss mid-upgrade, fresh overlay, config-preserving upgrade and upgrade without preserving config, entering trial boot, rejecting mismatched images, manual slot switch. Verification: all tests pass; `spec-coverage` shows no uncovered scenario in this change.

## 5. Static checks of what only the RK3399 runs

- [x] 5.1 Add the static tests to `tests/firmware/test_boot_rollback.py` (design D7): the built-in environments of the shipped U-Boot and `uboot-wrt-qemu` are identical apart from the board constants, and the R4S control device tree aliases `mmc1` to the SD card controller ("Compare the two bootloaders"); the U-Boot and kernel `.config` files and the built-in environment arm the watchdog chain ("Watchdog armed before the kernel"). Verification: both pass in `just test`; each fails when one of its options or constants is changed.
- [x] 5.2 Update the foundation's boot chain test in `tests/firmware/test_rootfs.py` for the factory image (firmware/rootfs, as modified here): the loader, the U-Boot FIT that boots with `run wrt_boot`, and the R4S device tree in the kernel FIT of both slots. Verification: the test passes on the factory image.

## 6. Documentation and migration

- [x] 6.1 Write `docs/ab-layout.md`: partition offsets, what each variable means, state transitions, and how to recover manually over the serial console. Verification: following the document, manually switching slots once at the emulator's U-Boot prompt succeeds.
- [x] 6.2 Write `docs/migration-single-to-ab.md`, matching the design's Migration Plan. Verification: following the document in the emulator, migrating from a single-slot image to the A/B factory image and restoring the backup leaves the config identical to before the migration.
