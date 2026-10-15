# Proposal

## Why

Main's CI run 38696888543 failed the R4S's `system` job in `test_rollback_after_three_unconfirmed_boots`. The emulator log that trial-boot-resilience added named the cause: `watchdog_perform_action` at 09:27:13, 1 min 46 s into the test, while it uploaded the upgrade image. The guest had printed `hrtimer: interrupt took 67702560 ns` just before. The reset put the router back on its first boot, the test's sysupgrade never ran, and the test waited 30 min for a rollback that could not come.

The router did not hang; the host starved it. GitHub's runners have 4 cores, and the emulator runs the board's 6 (R4S) or 8 (R6S) cores as as many host threads (multi-threaded TCG). Those threads wait for each other whenever one of them must work alone: code-cache flushes, and TLB flushes across cores. With more emulated cores than host cores, a descheduled thread holds up all the others, and on a slow runner the guest can stop for long stretches. QEMU's watchdog meanwhile counts host time: without instruction counting, the virtual clock follows the host's. When procd cannot ping within its 30 s timeout, the emulator resets a machine that a device, whose cores never wait for a host, would have kept running.

The same reset is the likeliest cause of the trial boots that came back on slot A in runs 37293958173 and 38252151081: both reset the machine without a message, 43 and 54 s into a trial boot, as the guest's work peaked. The VM, with 9 cores for the emulator, never reset that way in four full suites and eight trial boots under `stress-ng`.

## What Changes

- **A test that starves the emulator on purpose.** It confines QEMU to fewer host cores than the board has, keeps the guest busy for longer than the watchdog's timeout, and checks that the emulator logs no watchdog action and the router keeps its boot. It reproduces CI's runners on any host, before and after the fix.
- **The emulator runs the board's cores so that host load cannot stop the guest.** The way is chosen by measurement with that test (design D2). The candidates: one host thread for all emulated cores when the host has fewer cores than the board, instruction counting, which makes the virtual clock follow the guest's own progress, or tuning the multi-threaded mode. The guest keeps all of the board's cores in every case, and the device's watchdog configuration (procd's 30 s, U-Boot's and the kernel's) stays as it is.
- **The watchdog tests stay as they are.** "Userspace stops feeding the watchdog" and "Watchdog reset logged" still reset the guest when procd stops feeding it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `testing/emulation`: the emulator's watchdog resets the guest only when the guest stops feeding it, not when the host's load keeps the guest from running.

## Impact

- `tests/wrt_tests/device/emu.py`: how QEMU runs the board's cores; `tests/testing/test_emulation.py`: the starvation test; `tests/unit/test_emu.py`: the emulator's arguments.
- CI's and the VM's test runs: their duration changes with the mode the emulator runs in, measured in D2. The `system` jobs are already close to their 150 min limit on slow runners, so the measurement includes the suites' duration.
- No change to the firmware or the build.
