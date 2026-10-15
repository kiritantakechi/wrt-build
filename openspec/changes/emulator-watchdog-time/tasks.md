# Tasks

## 1. The reproduction (design D1)

- [ ] 1.1 Add the `testing/emulation` test "Busy guest on fewer host cores" to `tests/testing/test_emulation.py` (D1): QEMU's threads confined to half the board's cores in host cores, the guest kept busy for 60 s (the upgrade image uploaded, a CPU-bound loop on each guest core), affinity restored in a `finally`.

  Verify: `just check` passes; `spec-coverage --change emulator-watchdog-time` reports the scenario covered.
- [ ] 1.2 Run the test 10 times on each board on the VM with today's emulator (the D2 baseline).

  Verify: some runs log a `watchdog_perform_action` and reboot the router; record how many, per board, in design.md's Context. If none does, stop and look for the cause again.

## 2. How the emulator runs the board's cores (design D2, D3)

- [ ] 2.1 Measure the candidates of D2 in its order: the test 10 times, and `firmware/test_boot_rollback.py` and `firmware/test_ab_upgrade.py` timed with QEMU confined to 4 host cores, also with today's emulator for comparison.

  Verify: the results, and the candidate chosen by D2's criteria, recorded in design.md (D2).
- [ ] 2.2 Make `wrt_tests.device.emu` choose the chosen mode when the emulator starts, from the session's cores and the board's (D3), and add the unit test of the choice to `tests/unit/test_emu.py`.

  Verify: `just check` passes; the unit test covers hosts with more, as many and fewer cores than each board.
- [ ] 2.3 Describe in `docs/dev-setup.md` how the emulator runs the board's cores on a host with fewer cores, and why.

  Verify: `just check` passes.

## 3. Integration (design D4)

- [ ] 3.1 Run the test 10 times on each board with the change, then the full system tests on both boards (dev profile).

  Verify: 10 of 10 pass on each board with no watchdog action logged; all system tests pass on both boards.
- [ ] 3.2 Get a green CI run for both boards.

  Verify: record the run in `docs/ci.md`, with the suites' durations and the cause of runs 37293958173, 38252151081 and 38696888543.

## Workflow follow-up

- Sync the delta spec, archive the change, merge it to main and push Codeberg first, then GitHub.
