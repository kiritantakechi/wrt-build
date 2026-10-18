# Tasks

## 1. The test (design D3)

- [x] 1.1 Add the `build/boards` test "A fragment leaves a question for the next" (D3).

  Verify: `just check` passes; `spec-coverage --change uboot-config-merge` reports the scenario covered; the test fails on the VM's build tree without the patches.

## 2. The patch (design D1, D2)

- [x] 2.1 Add the two U-Boot Kconfig backports to uboot-rockchip's patches through the openwrt series' next patch, with `PKG_RELEASE` up, and their write-up in `docs/patches.md` (D1).

  Verify: `just check` passes.
- [x] 2.2 Have uboot-wrt-qemu take uboot-rockchip's patch directory, with `PKG_RELEASE` up (D2).

  Verify: both boards' and the emulator's U-Boot build, each `u-boot.config` the same as before; the test passes on both boards' build trees.
  Result (2026-10-18): `just build` of both boards built uboot-rockchip and uboot-wrt-qemu anew, the emulator's source with both Kconfig patches applied; the six U-Boot `.config` files of the two trees (each board's, the emulator's and the host tools') are the same as before. The test passes on both trees. With patch 120 alone, a first build had the merge end with `CONFIG_ENV_ADDR_REDUND=` empty, and `make oldconfig </dev/null` after it wrote 1.1 GB of prompts in 20 s, which led to patch 121.

## 3. Integration (design D4)

- [x] 3.1 Run the firmware/boot-rollback tests on both boards (dev profile).

  Verify: all pass.
  Result (2026-10-18): R4S 13 passed, R6S 13 passed, on the builds with both patches. A first run under the Mac's batch load (29 to 66) timed out throughout and was discarded.
- [ ] 3.2 Get a green CI run for both boards.

  Verify: record the run in `docs/ci.md`.

## Workflow follow-up

- Sync the delta spec, archive the change, merge it to main and push Codeberg first, then GitHub.
