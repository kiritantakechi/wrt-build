# Design

## Context

See proposal.md for why. The current state:

**The environment.**
- U-Boot keeps one copy at `0x3F8000`, 32 KiB, on the boot disk (`uboot/wrt-ab.config`), and reads only `boot_slot`, `bootcount` and `upgrade_available` from it (`ENV_WRITEABLE_LIST`). An invalid copy means U-Boot's built-in default, which boots slot A.
- The boot area leaves `0x400000` to `0x800000` free, between the end of the environment and `u-boot.itb` (`docs/ab-layout.md`); the tests' boot area, which an upgrade must leave alone, does not include it (`wrt_tests.device.ab.BOOT_AREA`).
- Linux reaches the environment through uboot-envtools: `31-wrt-ab` configures `ubootenv` with the offset and size written into it, once per slot unless an upgrade carried a configuration over. Three places write it: the sysupgrade hook (`/lib/upgrade/wrt-ab.sh`: the trial of the new slot), `wrt-slot switch`, and the health check's confirmation, all through `fw_setenv -s - && sync`.
- The bootloader passes `wrt.slot=` on the kernel command line, built in its environment text (`uboot/wrt-ab.env`). U-Boot preprocesses that text with its configuration, so it can name Kconfig values (`CONFIG_ENV_OFFSET`).

**The failures.** In both runs, slot B's trial boot was reset without a message at the time of the health check's confirmation, and U-Boot then read a corrupt environment and booted slot A (`emulator0/console.log` of the failed jobs, read boot by boot). Ruled out on the VM:
- a slow host disk: the A/B tests with the emulator on the work volume, whose flushes take up to a minute, passed four times out of four;
- an emulator stalled by its disk: the environment write throttled to 512 B/s for five minutes left the router running, its watchdog fed.

**The health check.** `wrt-healthcheck` loops until its checks pass or `time() - start` reaches `total` (300 s). The harness sets the router's clock when a boot is ready (`Router.set_clock`), from the time of the newest file in `/etc`, about two weeks behind in CI.

**The emulator.** QEMU has an `i6300esb` with `-action watchdog=reset`; the harness writes the serial console to `emulator<n>/console.log`, which CI uploads when a test fails. QEMU 11.1 traces `watchdog_perform_action` and `qemu_system_shutdown_request`.

## Goals / Non-Goals

**Goals:**
- No reset at any moment loses the A/B state, on the device or in the emulator.
- The next unexplained reset in the emulator names its cause.

**Non-Goals:**
- Updating the bootloader with an A/B upgrade: it changes with a factory image only.
- Reading the environment of a bootloader from before this change in the new layout, or the reverse (proposal: BREAKING).

## Decisions

### D1. Two copies of the environment

`uboot/wrt-ab.config` sets `CONFIG_ENV_REDUNDANT=y` and `CONFIG_ENV_OFFSET_REDUND=0x400000`, for every board and the emulator alike:
- U-Boot writes the older copy with a serial flag one higher, and reads the valid copy with the higher flag. A write cut short leaves the other copy, the previous state.
- Both invalid means the built-in default, slot A, as now (the factory image leaves both areas blank).
- `0x400000` follows the first copy in the free area, so the loader keeps its room below `0x3F8000`.
- `CONFIG_ENV_REDUNDANT_UPGRADE` stays off: it reads a single copy left by an older bootloader, and a new bootloader only arrives with a factory image, which blanks both areas.

Alternatives considered:
- **One copy, written more carefully** (`sync`, `O_DIRECT`): a block device writes 32 KiB in several requests; nothing makes the write of one copy atomic.
- **The state in a filesystem U-Boot reads**: a filesystem is a larger thing to keep consistent across a cut, and U-Boot's write support for it is weaker than its environment's.
- **The eMMC's boot partitions**: the R4S boots from an SD card, which has none.

### D2. The bootloader names its copies on the kernel command line

`wrt_boot` adds `wrt.env=CONFIG_ENV_SIZE@CONFIG_ENV_OFFSET,CONFIG_ENV_SIZE@CONFIG_ENV_OFFSET_REDUND` to `bootargs`, `size@offset` per copy as `mtdparts` writes it, and U-Boot's preprocessing turns the names into the values it was built with. The layout's one source is then `uboot/wrt-ab.config`:
- the system configures `fw_printenv` and `fw_setenv` from the bootloader that started it, so an image never writes a layout its bootloader cannot read;
- the offset written into `31-wrt-ab` goes.

Alternatives considered:
- **The offsets written into the image as well**: an image cannot tell a bootloader with one copy from one with two, and writing the two-copy layout for a bootloader with one corrupts its only copy.
- **The layout read off the disk**: a blank or corrupt area says nothing about which layout the bootloader expects.

### D3. The system writes only where it was told

- The ucode module `wrt.ab` gains `environment(cmdline)`: the copies of `wrt.env=` as `{ size, offset }`, from `/proc/cmdline` by default; null without the argument.
- `31-wrt-ab` adds one `ubootenv` section per copy (uboot-envtools makes two lines of `fw_env.config` a redundant environment). Without `wrt.env=` it configures nothing and logs why.
- The sysupgrade hook's `platform_check_image` refuses an upgrade while `fw_printenv` cannot read the environment, before anything is written, naming the cause; `wrt-slot switch` and the health check already fail when `setenv` does.
- A configuration an upgrade carries over stays, as now: it was made under the same bootloader, which upgrades do not change.

### D4. The health check's clock

`wrt-healthcheck` takes `start` and the elapsed time from `clock(true)`, the monotonic clock, in seconds. The recorded result keeps `time()`, the time of day an administrator reads (`wrt-slot status`).

### D5. The emulator logs its resets

- QEMU starts with `-trace watchdog_perform_action -trace qemu_system_shutdown_request -D emulator<n>/qemu.log`: each line carries the time and the action, the watchdog's or a shutdown or reset QEMU itself requests.
- CI's console artifact takes `qemu.log` with `console.log`.
- A reset without a line there and without a message on the console is then the guest's own, or a harness power cut, which the tests that cut the power know they did.

### D6. Tests

- `firmware/boot-rollback`:
  - "Persistent variable missing or corrupted": both copies overwritten.
  - "Environment write cut short": a trial of the other slot written (`boot_slot`, `upgrade_available=1`), then the confirmation written; the copy with the higher flag, which the confirmation went to, overwritten; after a reboot, the trial slot again, `upgrade_available` 1 and `bootcount` 1. With one copy this fails, as the confirmation overwrote the trial.
  - "Compare the two bootloaders": `CONFIG_ENV_REDUNDANT` and both offsets in each configuration.
  - "The environment where the bootloader names it": `wrt.env=` on the command line names the two places of `wrt_tests.device.ab`, and `fw_env.config` holds exactly those.
  - "A bootloader that names no environment": `environment()` of a command line without `wrt.env=` is null; with the environment's configuration removed, as such a bootloader leaves it, `sysupgrade` refuses and both slots stay as they were.
- `firmware/health-check` "Clock set during a trial boot": a registered check failing until a file exists, the trial state, the health check started with limits of 60 s total and 3 s interval; the clock set a day forward while the check fails, the file created after two more intervals; the slot is confirmed, and the boot ID unchanged.
- `testing/emulation` "Watchdog reset logged": userspace stops feeding the watchdog; after the reset, `qemu.log` holds the watchdog's action and the console no shutdown.

### D7. Verification

- The full system tests on both boards, then CI.
- The trial tests repeated on the VM under CPU load, where the network test's failure reproduced three times in ten: any reset there is named by `qemu.log`, and the trial survives it.

## Risks / Trade-offs

- [Existing development devices keep a bootloader with one copy] → Their upgrades refuse, naming the factory image as the way out (D3); no release is affected.
- [Every write now costs the other copy's area too] → One 32 KiB write per state change, as before: U-Boot and uboot-envtools write one copy at a time.
- [The cause of the emulator's reset stays unknown until it happens again] → D5 names it then; D1 makes the trial survive it meanwhile, and a reset that the logs show to be the emulator's own fault becomes a change of its own.

## Migration Plan

- A device gets the second copy by writing the factory image, which also blanks both areas: its first boot takes slot A, as every first boot does.
- Rollback: reverting the change restores one copy; a device written with the new factory image then needs the old factory image too.
