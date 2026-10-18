# Design

## Context

See proposal.md for why. The current state:
- `build.yml`'s `system-test` job runs per board and suite (matrix), with `timeout-minutes: 150`, each suite a list of paths under `tests/` for `just test <board> ci <paths>`: `system` (`build firmware quality testing unit`), `network`, `services` (`storage services`) and `release` (`release ops`).
- Each job spends 10 to 13 min before its first test: the runner, Nix, the artifacts and the emulator's first boot and snapshot.
- Main's run 39103498699, minutes per module in the `system` jobs (R4S / R6S): `test_ab_upgrade.py` 53 / 37, `test_boot_rollback.py` 34 / 26, `test_base_system.py` 8 / 6, `test_health_check.py` 6 / 5, `testing/test_emulation.py` 5 / 4, `test_rootfs.py` 4 / 3, `test_ab_layout.py` 3 / 2, `build/test_ci.py` 2 / 2, the rest under 2 together. The jobs took 128 and 97 min; `network` 29 to 35, `services` 36 to 48, `release` 39.
- Slow runners: 1.6 to 1.8 times as long throughout, setup included (runs 38595494438 and 38680078594).
- The test directories mirror the spec capabilities (`firmware/ab-upgrade` is `tests/firmware/test_ab_upgrade.py`), so a suite cannot take the A/B tests by directory without breaking that mirror.

## Goals / Non-Goals

**Goals:**
- Every system test job within its 150 min limit on a runner 1.8 times slower than usual, with room to grow.
- A test module never silently left out of CI, nor run twice.

**Non-Goals:**
- Faster A/B tests: each reboots the emulated board one or more times, which is what they test.
- A different limit.

## Decisions

### D1. Three suites from `system`

| Suite | Paths | Tests (R4S / R6S) |
|---|---|---|
| `upgrade` | `firmware/test_ab_upgrade.py firmware/test_ab_layout.py` | 56 / 39 min |
| `boot` | `firmware/test_boot_rollback.py firmware/test_health_check.py` | 40 / 31 min |
| `system` | `build firmware/test_base_system.py firmware/test_kernel.py firmware/test_rootfs.py firmware/test_toolchain.py quality testing unit` | 20 / 16 min |

With setup, the R4S's longest job takes about 70 min, and about 125 on a runner 1.8 times slower. The suites keep areas together: what an upgrade does, what a boot does, and the rest of the system. `network`, `services` and `release` stay.

Alternatives considered:
- **Move the A/B tests into a directory of their own**: the suite would select them by directory, but the tests would no longer mirror their capabilities' paths.
- **Split by recorded durations** (a pytest plugin balancing modules): the suites would change with the timings, and a failure would name no area.
- **Two suites** (`firmware` and the rest): the R4S's `firmware` would still take about 115 min of tests.

### D2. The partition test

`build/ci` "Every test in one job", in `tests/build/test_ci.py`: it reads the `system-test` matrix's suites from `build.yml`, expands each path (a directory selects every `test_*.py` under it, a file itself), and asserts that every `test_*.py` under `tests/`'s test directories is selected exactly once. A new module in `firmware/` that no suite names fails it, with its name.

### D3. Verification

- The partition test; `just check`.
- A CI run with the six suites per board: each job's time recorded in `docs/ci.md`, with the longest under 80 min on a usual runner.

## Risks / Trade-offs

- [More jobs] → Two more runners per board for the test stage, within the concurrency of a public repository; each pays the setup again, about 12 min of runner time, for about 20 min less wall time.
- [A new firmware module needs a suite] → The partition test names it.
