# Tasks

## 1. Bootloader (shared logic + two board builds)

- [ ] 1.1 Write `uboot/wrt-ab.env` (shared logic), plus the structurally symmetric `uboot/board-r4s.env` and `uboot/board-qemu.env` (containing only the constants listed in design D3), and register every runtime variable as writable. Verification: the code-standard checks confirm that the two board files contain exactly the same variable names, and only those variables.
- [ ] 1.2 Modify `package/boot/uboot-rockchip/Makefile` so the change applies only to the `nanopi-r4s-rk3399` variant: concatenate the environment file, and append the shared config and the r4s-specific config. Verification: the built U-Boot `.config` contains these options; the `.config` of every other rockchip variant is unchanged.
- [ ] 1.3 Add the `uboot-wrt-qemu` package to the in-house feed: build `qemu_arm64` from the same U-Boot source package, concatenate the qemu board constants and the shared logic, and append the shared config and the qemu-specific config; the artifact goes only into the test directory. Verification: the code-standard checks confirm that its `PKG_VERSION` and `PKG_HASH` match `uboot-rockchip`; `printenv` in QEMU shows `wrt_boot`.
- [ ] 1.4 Add `CONFIG_MMC_SDHCI_PCI=y` to the virt driver group in `config/kernel.config`, and fill in the sub-options with `listnewconfig`. Verification: the kernel config check passes after the build.

## 2. Images

- [ ] 2.1 Implement `scripts/gen_image_ab.sh`, and add a factory image rule to the rockchip image recipe (four partitions, zero-filled environment area). Verification: `tests/firmware/test_ab_layout.py` checks the order and sizes in the partition table and confirms the total size is within 4 GB.
- [ ] 2.2 Add a rule that builds the single-slot upgrade tar, with metadata attached. Verification: `test_ab_layout.py` checks that the tar contains only kernel, root, and CONTROL, and that the metadata names the correct board.

## 3. Linux side

- [ ] 3.1 Modify uboot-envtools to add the R4S config. Verification: in the emulator, `fw_printenv boot_slot` reads a value; after `fw_setenv`, `printenv` shows the change after rebooting into U-Boot.
- [ ] 3.2 Implement the `status` and `switch` subcommands of `wrt-slot` in the in-house feed. Verification: covered by the manual slot switch test in `test_boot_rollback.py`.
- [ ] 3.3 Implement `wrt-healthcheck`: built-in checks, the `/etc/healthcheck.d/` registration mechanism, per-check and total time limits, the JSON result, and handling for both the trial boot and confirmed states. Verification: `test_health_check.py` covers every scenario in the health-check spec.
- [ ] 3.4 Modify `platform_check_image`, `platform_do_upgrade`, and `platform_copy_config` in `platform.sh`, plus `79_move_config`. Verification: `test_ab_upgrade.py` covers every scenario in the ab-upgrade spec.

## 4. Emulator tests (all run in `just test`)

- [ ] 4.1 Extend the emulation environment to support A/B mode: load `uboot-wrt-qemu` with `-bios`, attach the factory image as the SD card through `sdhci-pci`, and allow disk writes to be throttled (for power-loss tests). Verification: the emulator self-tests cover boot, power loss, and reboot in A/B mode.
- [ ] 4.2 Write `tests/firmware/test_ab_layout.py`, covering every scenario in the ab-layout spec (the 4 GB scenario is judged by image size). Verification: all tests pass.
- [ ] 4.3 Write `tests/firmware/test_boot_rollback.py`, covering these scenarios: slot selection for a, b, and an invalid value; the persistent environment cannot override boot logic; rollback after three failed trial boots; no counting during normal operation; switching slots within the same power cycle on a load failure; stopping at the prompt when both slots fail; reboot and count within 10 seconds after a kernel panic. Verification: all tests pass.
- [ ] 4.4 Write `tests/firmware/test_health_check.py`: passes with WAN down, fails when uhttpd is not listening, a registered check fails or times out, handling for the trial boot and confirmed states, and the status query. Verification: all tests pass.
- [ ] 4.5 Write `tests/firmware/test_ab_upgrade.py`: writes only the inactive slot (checksums unchanged), power loss mid-upgrade, fresh overlay, config-preserving upgrade and upgrade without preserving config, entering trial boot, rejecting mismatched images, manual slot switch. Verification: all tests pass; `spec-coverage` shows no uncovered scenarios in this change other than the device-only ones.

## 5. Device smoke test

- [ ] 5.1 Write `@target("device")` tests: U-Boot boots from the SD card and enters the slot named by `boot_slot`; the watchdog resets the device on an early hang; the device resets when userspace does not take over. When a power cut or a simulated hang is needed, the test prompts for the manual step. Verification: when run on the emulator, these tests are skipped and show the reason.
- [ ] 5.2 Flash the factory image to the SD card and run `just test-device <host>`. Verification: the report shows everything passing, and the results are archived to `docs/validation/ab-rollback-device.md`.

## 6. Documentation and migration

- [ ] 6.1 Write `docs/ab-layout.md`: partition offsets, what each variable means, state transitions, and how to recover manually over the serial console. Verification: following the document, manually switching slots once at the emulator's U-Boot prompt succeeds.
- [ ] 6.2 Write `docs/migration-single-to-ab.md`, matching the design's Migration Plan. Verification: following the document in the emulator, migrating from a single-slot image to the A/B factory image and restoring the backup leaves the config identical to before the migration.
