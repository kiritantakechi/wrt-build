# Tasks

## 1. The polling contract (design D1, D2, D3)

- [x] 1.1 Make `wrt_tests.model.poll.until` wait while the probe's answer is empty (D1), with its docstring; drop the `or None` of `wrt_tests.device.storage` and `tests/testing/test_emulation.py` (D2); and describe the contract in `docs/conventions.md`, next to the harness's layers.

  Verify: `just check` passes.
- [x] 1.2 Add the `testing/harness` tests "A probe answers empty first" and "No answer within the time limit" to `tests/testing/test_harness.py` (D3).

  Verify: both pass, and `spec-coverage --change harness-polling` reports no uncovered scenario.

## 2. Integration (design D4)

- [x] 2.1 Repeat the reproduction: `network/test_wan.py` ten times on the R4S on the VM, with `stress-ng --cpu 4` beside the emulator.

  Verify: ten of ten runs pass, where three of ten failed before (2026-10-14).
- [x] 2.2 Run the full system tests on both boards (dev profile).

  Verify: all tests pass on both boards.
- [x] 2.3 Get a green CI run for both boards.

  Verify: record the run in `docs/ci.md`, with the cause of the refused probes of runs 38102368454 and 38252151081.

## Workflow follow-up

- Sync the delta spec, archive the change, merge it to main and push Codeberg first, then GitHub.
