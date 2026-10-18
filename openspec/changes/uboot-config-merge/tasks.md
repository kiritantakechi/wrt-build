# Tasks

## 1. The test (design D3)

- [x] 1.1 Add the `build/boards` test "A fragment leaves a question for the next" (D3).

  Verify: `just check` passes; `spec-coverage --change uboot-config-merge` reports the scenario covered; the test fails on the VM's build tree without the patches.

## 2. The patch (design D1, D2)

- [x] 2.1 Add the two U-Boot Kconfig backports to uboot-rockchip's patches through the openwrt series' next patch, with `PKG_RELEASE` up, and their write-up in `docs/patches.md` (D1).

  Verify: `just check` passes.
- [ ] 2.2 Have uboot-wrt-qemu take uboot-rockchip's patch directory, with `PKG_RELEASE` up (D2).

  Verify: both boards' and the emulator's U-Boot build, each `u-boot.config` the same as before; the test passes on both boards' build trees.

## 3. Integration (design D4)

- [ ] 3.1 Run the firmware/boot-rollback tests on both boards (dev profile).

  Verify: all pass.
- [ ] 3.2 Get a green CI run for both boards.

  Verify: record the run in `docs/ci.md`.

## Workflow follow-up

- Sync the delta spec, archive the change, merge it to main and push Codeberg first, then GitHub.
