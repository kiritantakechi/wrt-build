# Proposal

## Why

While trial-boot-resilience was verified on the VM, the emulator's U-Boot build hung for two hours and filled the work volume. The A/B fragment had turned on a second environment copy (`CONFIG_ENV_REDUNDANT`), and the emulator's defconfig still kept the environment in flash, so Kconfig asked for the second copy's flash address (`ENV_ADDR_REDUND`), a hex value with no default. U-Boot merges each configuration fragment with `yes "" | make oldconfig`, and Kconfig asks a hex question again on every empty answer: the merge never ends, and the build's log of the prompts grew to 22 GB. trial-boot-resilience fixed its fragment, but any fragment that leaves such a question for the next one to settle hangs the build the same way.

Linux merges fragments with `make olddefconfig` since 2019 (3266c806dc86, "kconfig: run olddefconfig instead of oldconfig after merging fragments"), which asks nothing and leaves such a symbol unset. Upstream U-Boot still pipes `yes ""` into `oldconfig`.

## What Changes

- **U-Boot merges fragments without asking.** A U-Boot patch, the port of Linux's commit, runs `olddefconfig` after `merge_config.sh` in `scripts/kconfig/Makefile`'s `%.config` rule. It is meant for upstream (`Upstream-Status: Pending`), carried in uboot-rockchip's patches through the openwrt series, with its write-up in `docs/patches.md`.
- **The emulator's U-Boot takes the boards' patches.** uboot-wrt-qemu, which already takes its version and hash from uboot-rockchip so that the two builds cannot drift apart, also takes uboot-rockchip's patch directory: the emulator's U-Boot is built from the boards' source with the boards' patches, this one among them.
- **A test that merges a fragment leaving such a question.** On the emulator's prepared U-Boot source, a fragment that turns on the second environment copy must merge within a time limit, with the flash address left unset.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `build/boards`: a board's or the emulator's U-Boot merges its configuration fragments without asking, however a fragment leaves a question for the next one to settle.

## Impact

- `patches/openwrt`: a new patch adding the U-Boot patch to uboot-rockchip, `PKG_RELEASE` up; `feed/boot/uboot-wrt-qemu/Makefile`: the boards' patch directory, `PKG_RELEASE` up; `docs/patches.md`: the write-up.
- `tests/build/`: the merge test, which runs where a build tree with the emulator's U-Boot is present.
- The boards' and the emulator's U-Boot: built again; their configurations are unchanged.
