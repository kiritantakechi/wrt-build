# Tasks

## 1. Two copies of the environment, named by the bootloader (design D1, D2, D3)

- [ ] 1.1 Set `CONFIG_ENV_REDUNDANT` and `CONFIG_ENV_OFFSET_REDUND=0x400000` in `uboot/wrt-ab.config` (D1), and add `wrt.env=` to `wrt_boot`'s `bootargs` in `uboot/wrt-ab.env` from the configuration's values (D2).

  Verify: both boards' U-Boot and the emulator's build; their configurations hold both offsets; the kernel command line in the emulator reads `wrt.env=0x8000@0x3F8000,0x8000@0x400000` (case as U-Boot prints it).
- [ ] 1.2 Add `environment(cmdline)` to the ucode module `wrt.ab`; configure `ubootenv` from it in `31-wrt-ab`, without the written-in offset; refuse an upgrade in `platform_check_image` while the environment cannot be read (D3). Bump `wrt-ab`'s `PKG_RELEASE`.

  Verify: `just check`; on the emulator, `fw_env.config` holds the two copies, and `fw_setenv` then `fw_printenv` round-trip.
- [ ] 1.3 Update `wrt_tests.device.ab` (both offsets, the boot area) and the `firmware/boot-rollback` tests (D6): "Persistent variable missing or corrupted", "Environment write cut short", "Compare the two bootloaders", "The environment where the bootloader names it", "A bootloader that names no environment". Update `docs/ab-layout.md` (the layout, the two copies, the command line).

  Verify: the `firmware/boot-rollback`, `firmware/ab-upgrade` and `firmware/ab-layout` tests pass on both boards; "Environment write cut short" fails with the old single copy, as checked once by building with `CONFIG_ENV_REDUNDANT` off.

## 2. The health check's clock (design D4)

- [ ] 2.1 Measure `wrt-healthcheck`'s time limits on `clock(true)` (D4), and add the `firmware/health-check` test "Clock set during a trial boot" (D6).

  Verify: the test fails with `time()` and passes with `clock(true)`; the `firmware/health-check` tests pass on both boards.

## 3. The emulator's log of resets (design D5)

- [ ] 3.1 Start QEMU with the traces of its watchdog's actions and its own shutdown and reset requests into `qemu.log` beside the console log (D5); add it to CI's console artifact in `build.yml`; add the `testing/emulation` test "Watchdog reset logged" (D6).

  Verify: the test passes on both boards; `qemu.log` of a normal run holds no watchdog action.

## 4. Integration (design D7)

- [ ] 4.1 Run the full system tests on both boards (dev profile), then the trial tests eight times on the R4S under `stress-ng --cpu 4`.

  Verify: all tests pass; every reset in the repeated runs is either named in `qemu.log` or a harness power cut, and every trial ends confirmed on the new slot. Record what `qemu.log` named, if anything, in `docs/ci.md`.
- [ ] 4.2 Get a green CI run for both boards.

  Verify: record the run in `docs/ci.md`, with the cause found for runs 37293958173 and 38252151081.

## Workflow follow-up

- Sync the delta specs, archive the change, merge it to main and push Codeberg first, then GitHub.
