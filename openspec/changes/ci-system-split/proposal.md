# Proposal

## Why

CI's `system` test job runs `build firmware quality testing unit` for a board in one job with a 150 min limit. It took 72 to 128 min on usual runners, and runners are sometimes 1.6 to 1.8 times slower throughout: in run 38595494438 the R6S's job ran out of its limit 25 % through, and in main's run 39103498699 the R4S's took 128 of its 150 min. The A/B tests fill most of it: on the R4S, `firmware/test_ab_upgrade.py` took 53 min and `firmware/test_boot_rollback.py` 34, of 116 min of tests after 12 min of setup.

Raising the limit would let a hung job run longer before it is noticed. The job does too much for one runner.

## What Changes

- **Three jobs where the `system` job was, per board.** `upgrade` runs the A/B upgrade and layout tests, `boot` the boot rollback and health check tests, and `system` the rest: build, the other firmware tests, quality, testing and unit. On the R4S that is about 56, 40 and 20 min of tests, each well within the 150 min limit on a runner 1.8 times slower. `network`, `services` and `release` stay as they are.
- **Every test in exactly one job.** A test reads the matrix in `build.yml` and checks that the suites together select every test module once. A new test module that no suite names, or that two name, fails it.
- **`docs/ci.md`** describes the six test jobs per board.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `build/ci`: CI runs every system test of a board once, in jobs that each finish within their time limit with room for a slower runner.

## Impact

- `.github/workflows/build.yml`: the `system-test` matrix; the `upgrade-drill` gate needs no change, as it waits for the whole matrix.
- `tests/build/test_ci.py`: the suite test.
- `docs/ci.md`: the job table.
- CI uses two more runners per board for the test stage, and about 20 min less of wall time.
