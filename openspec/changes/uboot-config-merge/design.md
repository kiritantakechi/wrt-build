# Design

## Context

See proposal.md for why. The current state:
- OpenWrt's `include/u-boot.mk` configures a U-Boot variant with `make <defconfig>_config <fragment>.config...` (`UBOOT_CONFIG`). The boards' variants (uboot-rockchip) and the emulator's (uboot-wrt-qemu, in this repository's feed) add `wrt-ab.config` and `board-<id>.config` (`uboot/wrt-ab.mk`).
- U-Boot 2026.07's `scripts/kconfig/Makefile` merges each fragment with `merge_config.sh -m .config <fragment>`, then `yes "" | $(MAKE) -f $(srctree)/Makefile oldconfig`. `oldconfig` asks each new symbol; an empty answer takes the default, and a hex or int symbol without one is asked again, forever. Upstream U-Boot's master has the same rule.
- Linux replaced the `yes`/`oldconfig` pair with `olddefconfig` in 3266c806dc86 (v5.3, 2019): non-interactive, with the same result wherever a default exists, and a symbol without one left unset.
- uboot-wrt-qemu takes `PKG_VERSION` and `PKG_HASH` from uboot-rockchip's Makefile, but no patches: today it builds unpatched U-Boot, while uboot-rockchip carries eleven patches (rockchip boards and mkimage) and the A/B logic's glue.
- The hang that showed it, on 2026-10-15: `ENV_ADDR_REDUND` asked after `wrt-ab.config`, before `board-qemu.config` turned the flash environment off; trial-boot-resilience moved that line into `wrt-ab.config`.

## Goals / Non-Goals

**Goals:**
- No fragment can make a U-Boot configuration wait for an answer.
- The emulator's U-Boot built from the boards' source and patches.

**Non-Goals:**
- Other OpenWrt U-Boot packages: they carry their own patches; the patch is meant for U-Boot upstream, which fixes them all.
- Changing any fragment or configuration.

## Decisions

### D1. The U-Boot patch: Linux's change, ported

`scripts/kconfig/Makefile`'s `%.config` rule runs `$(Q)$(MAKE) -f $(srctree)/Makefile olddefconfig` after the merge, in place of `+$(Q)yes "" | $(MAKE) -f $(srctree)/Makefile oldconfig`, as Linux's 3266c806dc86 did. U-Boot's kconfig has the `olddefconfig` target. The merges that succeed today give the same configuration, since every symbol `yes ""` answered takes its default either way.

Alternatives considered:
- **Merge in OpenWrt's `include/u-boot.mk` instead** (`merge_config.sh`, then `olddefconfig`): it would cover every OpenWrt U-Boot package, but the fault is U-Boot's rule, and U-Boot's own `make <fragment>.config` would keep it.
- **Answer every question with a timeout**: the build would still wait, and an unset symbol is the answer the question deserves.

### D2. The patch's place, and the emulator's U-Boot

The openwrt series' next patch adds the U-Boot patch to `package/boot/uboot-rockchip/patches/` and raises uboot-rockchip's `PKG_RELEASE`. uboot-wrt-qemu sets `PATCH_DIR` to that directory, as it takes the version and hash from that package, and raises its `PKG_RELEASE`. The emulator's U-Boot then carries all of the boards' patches: rockchip board additions and mkimage changes, which do not touch `qemu_arm64`, and every patch to come.

### D3. The test

`build/boards` "A fragment leaves a question for the next", in `tests/build/`:
- Where the build tree holds the emulator's prepared U-Boot source (`build_dir/target-*_<board>/u-boot-wrt-qemu/u-boot-*`), the test copies it, puts a fragment with `CONFIG_ENV_REDUNDANT=y` in its `board/` directory, and runs `make qemu_arm64_defconfig <fragment>.config` in the build environment (`wrt-test-fhs`) with a time limit of a minute.
- It asserts that the merge ended within the limit, and that `.config` has `CONFIG_ENV_REDUNDANT=y` and no value for `CONFIG_ENV_ADDR_REDUND`.
- Without a build tree it skips, as the other tests of the build tree do; CI's test jobs have only the build's outputs.

### D4. Verification

- The test fails without the patch (the merge does not end) and passes with it.
- Both boards' and the emulator's U-Boot build, with the same `u-boot.config` as before (compared).
- The firmware/boot-rollback tests on both boards; CI.

## Risks / Trade-offs

- [A rockchip patch breaks the emulator's U-Boot] → D4 builds it; a patch that touched `qemu_arm64` would be a fault of that patch, to fix there.
- [`olddefconfig` and `yes ""` differ for a merge that works today] → They give the same configuration wherever a default exists, which D4 compares for all three U-Boot builds.
