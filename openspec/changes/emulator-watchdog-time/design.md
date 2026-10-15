# Design

## Context

See proposal.md for why. The current state:
- The emulator is QEMU's `virt` machine under TCG (no `-accel`, so the default), with the board's CPU model and all of its cores (`-smp 6` for the R4S, `-smp 8` for the R6S; `testing/emulation` "The board's cores"). TCG runs each emulated core in a host thread of its own (multi-threaded TCG).
- Its watchdog is an i6300esb with `-action watchdog=reset`. The model's timer counts `QEMU_CLOCK_VIRTUAL`, which follows the host's monotonic clock while the machine runs, unless QEMU counts instructions (`-icount`).
- procd feeds `/dev/watchdog` every 5 s with a 30 s timeout. The board's U-Boot arms its watchdog for 60 s, and the kernel keeps an open watchdog fed for 90 s (`watchdog.open_timeout=90`) until procd takes over. The emulator's U-Boot has no watchdog.
- Multi-threaded TCG makes all core threads stop and wait while one of them works alone: when the translated-code cache is flushed, and for TLB flushes across cores. A thread the host has descheduled holds up the others until the host runs it again.
- GitHub's runners have 4 cores. The VM has 9, more than either board has.
- The evidence:
  - Run 38696888543 (main, R4S `system`): `watchdog_perform_action` at 09:27:13, 1 min 46 s into `test_rollback_after_three_unconfirmed_boots`, while the test uploaded the upgrade image. The guest printed `hrtimer: interrupt took 67702560 ns` just before. The runner ran host-only tests 1.6 times slower than usual.
  - Runs 37293958173 and 38252151081 (R4S `system`): resets without a message, 43 and 54 s into a trial boot. qemu.log did not exist yet.
  - On the VM, no watchdog action outside the two tests that cause one, in four full suites and eight trial boots under `stress-ng --cpu 4`.

## Goals / Non-Goals

**Goals:**
- No watchdog reset from host load, on a host with any number of cores, while the guest keeps the board's cores.
- A test that reproduces the starvation on any host, with and without the fix.

**Non-Goals:**
- Changing the device's watchdog chain: U-Boot's, the kernel's, procd's timeouts.
- Changing the watchdog tests, which reset a guest whose procd stops feeding.
- Making the CI runners larger.

## Decisions

### D1. A test that starves the emulator

`testing/emulation` "Busy guest on fewer host cores", in `tests/testing/test_emulation.py`:
- It confines every QEMU thread (`/proc/<pid>/task/*`, `os.sched_setaffinity`) to half the board's cores in host cores: 3 for the R4S and 4 for the R6S, as many as or fewer than a runner gives.
- Then it keeps the guest busy for twice procd's timeout (60 s). It uploads the upgrade image, as in run 38696888543, and runs a CPU-bound loop on each guest core.
- It asserts that qemu.log gained no `watchdog_perform_action`, and that the router's boot ID is unchanged.
- It restores the threads' affinity to the cores the session runs on, also when it fails.

Confining the threads reproduces what a small or busy host does to the emulator, on any host, whatever its cores. It is the same arrangement before and after the fix, so it shows both.

Alternatives considered:
- **A CPU cgroup quota on the whole test run**: it needs a delegated cgroup, which neither the VM's user namespace nor CI sets up, and it slows the harness as well as the guest.
- **Host load from `stress-ng` only**: the VM's nine cores absorb it, as the eight trial boots under `stress-ng --cpu 4` showed.

### D2. How the emulator runs the board's cores: by measurement

Candidates, each of which keeps the board's cores in the guest:
1. **One host thread for all cores when the host has fewer cores than the board** (`-accel tcg,thread=single`), and multi-threaded TCG otherwise. No core waits for another core's host thread. The guest gets one host core's worth of time, steadily. The watchdog still counts host time, but nothing stops the guest for 30 s short of host overload.
2. **Instruction counting** (`-icount shift=auto`), which also implies one host thread. The virtual clock then follows the guest's own progress, so host load cannot trip the watchdog at all. The guest's clocks drift from the host's while the guest waits. Every run is slower than with candidate 1 on the VM's nine cores, where the cores run in parallel today.
3. **Multi-threaded TCG with a larger code cache** (`tb-size`), for fewer flushes. TLB flushes across cores remain, so it can only reduce the waits.

The measurement, on the VM, in this order, stopping at the first candidate that meets both criteria:
- The baseline: the D1 test 10 times with today's emulator. At least some runs must reset, or the reproduction does not hold and the cause is looked for again.
- Each candidate: the D1 test 10 times, and `firmware/test_boot_rollback.py` and `firmware/test_ab_upgrade.py` with QEMU confined to 4 host cores, as on a runner, timed.
- Criteria: no watchdog action in the 10 runs, and the two modules no slower than today's on 4 host cores. If none meets both, the one without resets that loses the least time.

Expected: candidate 1. It removes the waits between cores, and on 4 host cores one well-fed thread may not lose against six or eight threads that keep stopping each other. Candidate 2 is the fallback, if a single thread still stalls.

### D3. Where the choice lives

`wrt_tests.device.emu` decides when the emulator starts, from the cores the session may run on (`os.sched_getaffinity(0)`) and the board's cores, and passes the arguments to QEMU. It does not store them with the prepared emulator files: those are keyed by image, firmware and board and reused across sessions, on hosts with different cores. A unit test in `tests/unit/test_emu.py` covers the choice for a host with more, as many, and fewer cores than each board has.

### D4. Verification and records

- D1's test fails without the fix (the D2 baseline) and passes with it, 10 of 10 times on each board.
- The full system tests on both boards (dev profile).
- CI: a green run on both boards. `docs/ci.md` records the cause of runs 37293958173, 38252151081 and 38696888543, and the suites' durations under the new mode.
- `docs/dev-setup.md`: how the emulator runs the board's cores on a host with fewer cores, and why.

## Risks / Trade-offs

- [The reproduction does not reproduce] → The D2 baseline must reset before any candidate is judged; if it does not, the cause is looked for again, with the D1 test as the tool.
- [One host thread makes CI's suites slower, and the `system` jobs are close to their 150 min limit] → D2 measures the A/B modules under a runner's 4 cores. If the change costs time, the jobs' split (a separate task) goes first.
- [A test that changes the emulator's host affinity leaves it confined after a failure] → It restores the affinity in a `finally`, and the next session starts a new QEMU anyway.
- [The guest's clocks drift from the host's under instruction counting (candidate 2)] → The harness sets the router's clock after each snapshot restore already, and the tests measure time on the host.
