# Proposal

## Why

The A/B tests fail now and then in CI's R4S `system` suite: after an upgrade, the router comes back on slot A where the new slot B should be on trial (`test_upgrade_keeps_the_configuration` in run 37293958173, `test_upgrade_boots_the_new_slot_on_trial` in run 38252151081). The emulator's console shows the same sequence both times:
- slot B's trial boot runs until the LAN is up, 43 and 54 s in, when init completes and the health check confirms the slot by writing U-Boot's environment;
- the machine resets without any message: no shutdown, no panic;
- U-Boot finds its stored environment corrupt (`bad CRC`), uses its built-in default and boots slot A.

Only the health check writes the environment during a trial boot, so the reset cut its write short. The environment has one copy, rewritten in place. Any reset during a write corrupts it and loses the A/B state, on a device as in the emulator: a power cut while the slot is confirmed, the watchdog during a hang, U-Boot's own bootcount update. Depending on which slot is which, the device then rolls a good upgrade back, or boots an unconfirmed slot with no trial and no rollback.

What reset the emulator is not established. The harness forces resets only in the power-loss tests, and the emulator logs nothing of its watchdog, so such a reset leaves no trace. Writes stalled for minutes on the VM did not trip the watchdog.

Found on the way: the health check measures its time limit on the wall clock. The harness sets the router's clock at every boot, as NTP does in service, and a clock set forward during a trial makes the check give up at once if its checks are still failing.

## What Changes

- **U-Boot keeps two copies of its environment** (`uboot/wrt-ab.config`), at `0x3F8000` and `0x400000`. A write goes to the older copy, so a write cut short leaves the newer one, the previous state, in effect.
- **The bootloader tells the system where its copies are.** It passes their sizes and offsets on the kernel command line, as it passes the running slot. `fw_printenv` and `fw_setenv` are configured from that alone. A system started by a bootloader that does not tell refuses to write the environment, rather than write it in a layout that bootloader cannot read.
- **The emulator logs what its watchdog does**, and every reset or shutdown QEMU itself requests, next to the console log. CI uploads that log with the console's when a test fails.
- **The health check measures its time limits on the boot's monotonic clock**, which setting the time of day does not move.
- **BREAKING (development builds only)**, as the bootloader changes only with a factory image and no release has shipped the old layout:
  - an image from after this change, booted by a bootloader from before it, refuses to upgrade until the factory image is written;
  - an image from before it, booted by a bootloader from after it, writes the environment in the single-copy layout, which the new bootloader ignores.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `firmware/boot-rollback`: the stored environment has two copies, and a write cut short leaves the previous state in effect; the bootloader names its copies to the system.
- `firmware/health-check`: the time limits run on the monotonic clock.
- `testing/emulation`: the emulator logs its watchdog's actions and the resets it requests.

## Impact

- `uboot/wrt-ab.config`, `uboot/wrt-ab.env`: the second copy, and its announcement on the kernel command line.
- `feed/utils/wrt-ab`: the ucode module reads the announcement, the uci-defaults configure `fw_env.config` from it, and the sysupgrade hook refuses to start without it; `wrt-healthcheck`'s clock.
- `tests/wrt_tests/device/emu.py`, `tests/wrt_tests/device/ab.py`, `.github/workflows/build.yml`: the emulator's log, the environment's two places, the uploaded artifact.
- `tests/firmware/test_boot_rollback.py`, `tests/firmware/test_health_check.py`, `tests/testing/test_emulation.py`: the scenarios.
- `docs/ab-layout.md`: the layout and the states.
- The bootloader changes only with a factory image, so a device gets the second copy by writing the factory image again.
