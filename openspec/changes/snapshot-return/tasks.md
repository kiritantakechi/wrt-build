# Tasks

## 1. The test (design D3)

- [x] 1.1 Add the `testing/emulation` test "Back from failsafe mode" to `tests/testing/test_emulation.py` (D3).

  Verify: `just check` passes; `spec-coverage --change snapshot-return` reports the scenario covered; the test fails on the R6S without the fix.
  Result (2026-10-19): without the fix, the return took 69 s on the R6S (the limit was 15 s then, 25 s since); firmware/base-system's failsafe test, now on `Router.reboot_into_failsafe()`, passed.

## 2. The return to the snapshot (design D1, D2)

- [x] 2.1 Have `Router.reset()` forget the router's link-layer address after `loadvm` (D1), and `set_clock()` connect first, set the time and check it (D2).

  Verify: `just check` passes; the test passes on both boards; CI's R6S image in CI's order passes three sessions.
  Result (2026-10-19): the test passes on both boards (with the failsafe test and `tests/testing/test_harness.py`, 27 passed each). CI's R6S image of run 39177086857, in CI's order of `firmware/test_base_system.py`'s first three tests, passed three sessions of three, where five of five had failed.

## 3. Integration (design D4)

- [ ] 3.1 Run the testing and firmware suites on both boards (dev profile).

  Verify: all pass.
- [ ] 3.2 Get a green CI run for both boards.

  Verify: record the run in `docs/ci.md`, with the cause of runs 39120617912 and 39177086857.

## Workflow follow-up

- Sync the delta spec, archive the change, merge it to main and push Codeberg first, then GitHub.
