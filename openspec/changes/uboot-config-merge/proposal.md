# Proposal

## Why

While trial-boot-resilience was verified on the VM, the emulator's U-Boot build hung for two hours and filled the work volume. The A/B fragment had turned on a second environment copy (`CONFIG_ENV_REDUNDANT`), and the emulator's defconfig still kept the environment in flash, so Kconfig asked for the second copy's flash address (`ENV_ADDR_REDUND`), a hex value with no default. U-Boot merges each configuration fragment with `yes "" | make oldconfig`, and Kconfig asks a hex question again on every empty answer: the merge never ends, and the build's log of the prompts grew to 22 GB. trial-boot-resilience fixed its fragment, but any fragment that leaves such a question for the next one to settle hangs the build the same way.

U-Boot's Kconfig lags Linux's in two fixes, both by Masahiro Yamada:
- Linux merges fragments with `make olddefconfig` since 2019 (3266c806dc86, "kconfig: run olddefconfig instead of oldconfig after merging fragments"). Upstream U-Boot still pipes `yes ""` into `oldconfig`.
- Linux gives an int or hex symbol without a default the value zero since 6.8 (6262afa10ef7, "kconfig: default to zero if int/hex symbol lacks default property"). U-Boot's leaves it empty, which no answer settles. With the merge fixed alone, the `oldconfig` that OpenWrt's `include/u-boot.mk` runs after its own `scripts/config` changes asks the same question at the end of its input, for ever: 1.1 GB of prompts in 20 s on the VM.

## What Changes

- **U-Boot's Kconfig asks no question a fragment leaves.** Two U-Boot patches backport Linux's commits: the `%.config` rule runs `olddefconfig` after `merge_config.sh`, and an int or hex symbol without a default is zero. They are meant for upstream (`Upstream-Status: Pending`), carried in uboot-rockchip's patches through the openwrt series, with their write-up in `docs/patches.md`.
- **The emulator's U-Boot takes the boards' patches.** uboot-wrt-qemu, which already takes its version and hash from uboot-rockchip so that the two builds cannot drift apart, also takes uboot-rockchip's patch directory: the emulator's U-Boot is built from the boards' source with the boards' patches, these among them.
- **A test that configures with a fragment leaving such a question.** On the emulator's prepared U-Boot source, a fragment that turns on the second environment copy must merge within a time limit with the flash address at zero, an `oldconfig` without input after it must end, and a later fragment's address must replace the zero.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `build/boards`: a board's or the emulator's U-Boot is configured from its fragments without asking, however a fragment leaves a question for the next one to settle.

## Impact

- `patches/openwrt`: a new patch adding the two U-Boot patches to uboot-rockchip, `PKG_RELEASE` up; `feed/boot/uboot-wrt-qemu/Makefile`: the boards' patch directory, `PKG_RELEASE` up; `docs/patches.md`: the write-up.
- `tests/build/`: the configuration test, which runs where a build tree with the emulator's U-Boot is present.
- The boards' and the emulator's U-Boot: built again; their configurations are unchanged, as none has a number without a value today.
