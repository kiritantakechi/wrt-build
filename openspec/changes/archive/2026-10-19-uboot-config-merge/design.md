# Design

## Context

See proposal.md for why. The current state:
- OpenWrt's `include/u-boot.mk` configures a U-Boot variant with `make <defconfig>_config <fragment>.config...` (`UBOOT_CONFIG`), then, when the package sets `UBOOT_CUSTOMIZE_CONFIG`, changes `.config` with `scripts/config` and runs `make oldconfig`. The boards' variants (uboot-rockchip) and the emulator's (uboot-wrt-qemu, in this repository's feed) add `wrt-ab.config` and `board-<id>.config` (`uboot/wrt-ab.mk`), and both packages set `UBOOT_CUSTOMIZE_CONFIG`.
- U-Boot 2026.07's `scripts/kconfig/Makefile` merges each fragment with `merge_config.sh -m .config <fragment>`, then `yes "" | $(MAKE) -f $(srctree)/Makefile oldconfig`. `oldconfig` asks each new symbol; an empty answer takes the default. Upstream U-Boot's master has the same rule.
- U-Boot's Kconfig gives an int or hex symbol without a default an empty value, which is not a valid one: `oldconfig` and `syncconfig` ask it, and an empty answer, or the end of the input, leaves it empty, so they ask again, for ever. Measured on the VM with the merge fixed: `make oldconfig </dev/null` after a merge that left `ENV_ADDR_REDUND` empty wrote 1.1 GB of prompts in 20 s.
- Linux fixed both: the merge runs `olddefconfig` since 3266c806dc86 (v5.3, 2019), and such a symbol is zero since 6262afa10ef7 (v6.8). Each is a small change, and U-Boot's Kconfig, synchronized with an older Linux, has neither.
- uboot-wrt-qemu takes `PKG_VERSION` and `PKG_HASH` from uboot-rockchip's Makefile, but no patches: today it builds unpatched U-Boot, while uboot-rockchip carries eleven patches (rockchip boards and mkimage) and the A/B logic's glue.
- The hang that showed it, on 2026-10-15: `ENV_ADDR_REDUND` asked after `wrt-ab.config`, before `board-qemu.config` turned the flash environment off; trial-boot-resilience moved that line into `wrt-ab.config`.

## Goals / Non-Goals

**Goals:**
- No fragment can make a U-Boot configuration wait for an answer, in the merge or after it.
- The emulator's U-Boot built from the boards' source and patches.

**Non-Goals:**
- Other OpenWrt U-Boot packages: they carry their own patches; the patches are meant for U-Boot upstream, which fixes them all.
- Changing any fragment or configuration.
- A default that fails its own validation (a hex default on an int symbol): a fault of the Kconfig file, not of a fragment. Linux's kbuild has a patch that stops `oldconfig` with an error at the end of its input in that case (Simon Glass, July 2026), not yet in a release.

## Decisions

### D1. The U-Boot patches: Linux's two commits, backported

- `120-kconfig-run-olddefconfig-after-merging-fragments.patch`, Linux's 3266c806dc86 as it is: the `%.config` rule runs `$(Q)$(MAKE) -f $(srctree)/Makefile olddefconfig` after the merge, in place of `+$(Q)yes "" | $(MAKE) -f $(srctree)/Makefile oldconfig`. The merge asks nothing, by construction; wherever `yes ""` ended, it gives the same configuration.
- `121-kconfig-default-to-zero-if-int-hex-symbol-lacks-default.patch`, Linux's 6262afa10ef7: an int symbol without a default is `0`, a hex one `0x0`, in `sym_calc_value()` and `sym_get_string_default()`. U-Boot's `sym_calc_value()` starts a number from `symbol_empty`, as Linux's did before a later refactoring, so its two cases set the tristate too; the rest is Linux's change.

Each keeps Linux's author, date and message, with a note on what it does in U-Boot. Together, a fragment's number is zero until a later fragment sets it, and no step after the merge asks for it.

Alternatives considered:
- **`olddefconfig` alone**: the merge ends, but the `oldconfig` after `include/u-boot.mk`'s own changes, or the build's `syncconfig`, asks the empty number for ever (measured above).
- **Stop at the end of input** (a 2023 Linux series): Linux dropped it, as it broke builds that run make with stdin from /dev/null, and chose the zero default instead.
- **OpenWrt's `FAIL_ON_UNCONFIGURED`** (its kernel's Kconfig hack, which exits when asked without a terminal): specific to OpenWrt, not meant for upstream, and a failed build where Linux builds.
- **Merge in OpenWrt's `include/u-boot.mk` instead** (`merge_config.sh`, then `olddefconfig`): the fault is U-Boot's, and U-Boot's own `make <fragment>.config` would keep it.

### D2. The patches' place, and the emulator's U-Boot

The openwrt series' next patch adds the U-Boot patches to `package/boot/uboot-rockchip/patches/` and raises uboot-rockchip's `PKG_RELEASE`. uboot-wrt-qemu sets `PATCH_DIR` to that directory, as it takes the version and hash from that package, counts it among its file dependencies (`PKG_FILE_DEPENDS`), so a changed patch prepares its source again, and raises its `PKG_RELEASE`. The emulator's U-Boot then carries all of the boards' patches: rockchip board additions and mkimage changes, which do not touch `qemu_arm64`, and every patch to come.

### D3. The test

`build/boards` "A fragment leaves a question for the next", in `tests/build/`:
- Where the build tree holds the emulator's prepared U-Boot source (`build_dir/target-*_<board>/u-boot-wrt-qemu/u-boot-*`), the test copies it and puts two fragments in its `board/` directory: one with `CONFIG_ENV_REDUNDANT=y`, one with a `CONFIG_ENV_ADDR_REDUND` value.
- In the build environment (`wrt-test-fhs`), without input and each within a minute: `make qemu_arm64_defconfig <first>.config` gives `CONFIG_ENV_REDUNDANT=y` and `CONFIG_ENV_ADDR_REDUND=0x0`; `make oldconfig` after it ends with the same values, as `include/u-boot.mk`'s does; `make qemu_arm64_defconfig <first>.config <second>.config` gives the second fragment's address.
- Without a build tree it skips, as the other tests of the build tree do; CI's test jobs have only the build's outputs.

### D4. Verification

- The test fails without the patches (the merge does not end), and passes with them.
- Both boards' and the emulator's U-Boot build, with the same `u-boot.config` as before (compared).
- The firmware/boot-rollback tests on both boards; CI.

## Risks / Trade-offs

- [A rockchip patch breaks the emulator's U-Boot] → D4 builds it; a patch that touched `qemu_arm64` would be a fault of that patch, to fix there.
- [`olddefconfig` and `yes ""` differ for a merge that works today] → They give the same configuration wherever `yes ""` ends, which D4 compares for all three U-Boot builds.
- [A number that no fragment sets now builds as zero, where the build used to hang] → Linux's choice since 6.8; the boards' fragments set every number they use, and the configurations D4 compares have no empty number today.
