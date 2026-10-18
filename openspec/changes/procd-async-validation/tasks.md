# Tasks

## 1. The test (design D4)

- [x] 1.1 Add the `firmware/ab-upgrade` test "A validation slower than the watchdog" to `tests/firmware/test_ab_upgrade.py` (D4).

  Verify: `just check` passes; `spec-coverage --change procd-async-validation` reports the scenario covered; the test fails on the R4S with today's procd.

## 2. procd (design D1, D2, D3)

- [x] 2.1 Write the procd patch that validates firmware images in the event loop (D1, D2), as `patches/openwrt/0039-procd-validate-firmware-images-without-blocking.patch` with `PKG_RELEASE` 3, and its write-up in `docs/patches.md` (D3).

  Verify: procd builds for both boards with no new warning; `just check` passes.
- [x] 2.2 Run the test on both boards with the patch.

  Verify: it passes on both boards.

## 3. Integration (design D5)

- [x] 3.1 Run the CI-like reproduction on the R4S twice, then the full system tests on both boards (dev profile).

  Verify: no watchdog action outside the tests that cause one in both reproductions, whose failures are only the harness's boot deadline; all system tests pass on both boards.
  Result (2026-10-18): both reproductions without a watchdog action, where seven to nine a run had reset the router before; six of their nine tests each ran out of the harness's boot deadline ("procd never reported init complete"), as the new slot's first boot is slower on four slowed cores than the deadline allows, which the patch does not change. The full suites passed: R4S 419, R6S 420, each with the two watchdog actions of the tests that cause one.
- [x] 3.2 Get a green CI run for both boards.

  Verify: record the run in `docs/ci.md`, with the cause of runs 37293958173, 38252151081 and 38696888543.

## Workflow follow-up

- Sync the delta spec, archive the change, merge it to main and push Codeberg first, then GitHub.
