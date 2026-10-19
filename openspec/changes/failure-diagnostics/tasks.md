# Tasks

## 1. The tests (design D4)

- [ ] 1.1 Add the `testing/harness` tests "A reboot that does not come" and "A failing test with the router online" to `tests/testing/test_harness.py` (D4).

  Verify: `just check` passes; `spec-coverage --change failure-diagnostics` reports both scenarios covered.

## 2. The diagnostics (design D1, D2, D3)

- [ ] 2.1 Keep a detached command's output on the router, and add the notes of a reboot that does not come (D1, D2).

  Verify: `just check` passes; the first test passes on both boards.
- [ ] 2.2 Add `Online.state()`, `Isp.log()` and the hook that adds the datapath section (D3).

  Verify: `just check` passes; the second test passes on both boards.

## 3. Integration (design D5)

- [ ] 3.1 Read the reports of a deliberately failing online test and a deliberately missing reboot on the VM.

  Verify: they show what D2 and D3 say.
- [ ] 3.2 Get a green CI run for both boards, with snapshot-return.

  Verify: record the run in `docs/ci.md`.

## Workflow follow-up

- Sync the delta spec, archive the change, merge it to main and push Codeberg first, then GitHub.
