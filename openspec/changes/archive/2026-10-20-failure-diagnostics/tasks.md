# Tasks

## 1. The tests (design D4)

- [x] 1.1 Add the `testing/harness` tests "A reboot that does not come" and "A failing test with the router online" to `tests/testing/test_harness.py` (D4).

  Verify: `just check` passes; `spec-coverage --change failure-diagnostics` reports both scenarios covered.

## 2. The diagnostics (design D1, D2, D3)

- [x] 2.1 Keep a detached command's output on the router, and add the notes of a reboot that does not come (D1, D2).

  Verify: `just check` passes; the first test passes on both boards.
- [x] 2.2 Add `Online.state()`, `Isp.log()` and the hook that adds the datapath section (D3).

  Verify: `just check` passes; the second test passes on both boards.
  Result (2026-10-19): both tests pass on both boards, with the rest of `tests/testing/test_harness.py`.

## 3. Integration (design D5)

- [x] 3.1 Read the reports of a deliberately failing online test and a deliberately missing reboot on the VM.

  Verify: they show what D2 and D3 say.
  Result (2026-10-19, R6S): the online test's report has a "datapath" section with both clients' addresses and routes (the IPv6 default route with its expiry), the router's `ifstatus wan` and `wan6` with their uptimes, its log lines of pppd and odhcpd ("No default route present, setting ra_lifetime to 0!" while it dialled), and the ISP's session and pppd log. The missing reboot's `TimeoutError` names the command, its output at 10.0.0.1 and the console since.
- [x] 3.2 Get a green CI run for both boards, with snapshot-return.

  Verify: record the run in `docs/ci.md`.
  Result (2026-10-19): run 39312523546 passed, the upgrade drill included.

## Workflow follow-up

- Sync the delta spec, archive the change, merge it to main and push Codeberg first, then GitHub.
