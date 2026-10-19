# Design

## Context

See proposal.md for why. The current state:
- `Router.detach(command)` runs `(command) >/dev/null 2>&1 </dev/null &` over SSH, for commands that end in a reboot (`reboot`, `sysupgrade`). `Router.wait_rebooted()` polls the boot ID until it changes and fails with "the router never rebooted"; `Router.reboot()` detaches and waits. Tests that move the router's LAN address wait inside `Router.moved_to()`.
- The emulator's console is recorded for the whole session (`Console.mark()`, `Console.text(since)`), and uploaded by CI when a test fails, with QEMU's log.
- `Online` (services/datapath) holds the router, the ISP handle, the sandbox network and the session; the `online` fixture and those built on it (`internet_zone`, `dae`, `trusted_ca`, ...) are module-scoped. `Isp` reads its sessions from the registry its scripts keep; its pppd logs to `pppd.log` in its working directory.
- pytest's report of a failed test carries named sections (`report.sections`), which the terminal summary and the JUnit report show with the failure.

## Goals / Non-Goals

**Goals:**
- The two failures of the proposal, had they shown these, would have named their cause or ruled out a mechanism at once.
- Gathering never fails a passing test nor hides the original failure.

**Non-Goals:**
- Streaming the router's log for the whole session: the state at the failure answers the questions at hand, at no cost to passing tests.
- A fix for the IPv6 failure: its cause stays unknown until a failure shows it (the freeze mechanism is recorded in the proposal).

## Decisions

### D1. Detached commands keep their output

`Router.detach()` runs `(command) >/tmp/wrt-detached.log 2>&1 </dev/null &` and remembers the command, the address it ran at and the console's mark. `/tmp` is in memory: the reboot the command leads to clears the file, and only a command that did not reboot the router leaves it.

### D2. The notes of a reboot that does not come

When `wait_rebooted()` runs out of time, its `TimeoutError` gets notes:
- the detached command, if any;
- its output, read at the address it ran at (`moved_to` that address for the read), or that no system answered there;
- the console since the command ran, its last 60 lines.

Each part that cannot be had says so; the timeout stays the error.

### D3. The datapath section

`Online.state()` returns the datapath's state as text: each LAN client's `ip addr` and IPv4 and IPv6 routes; the router's `ifstatus wan` and `ifstatus wan6` (up, uptime, addresses and prefixes) and its log lines of pppd, odhcp6c, odhcpd and netifd; the ISP's sessions and the end of its pppd log (`Isp.log()`). Each part is read on its own; a part that fails is replaced by its error.

A hook wrapper of `pytest_runtest_makereport` in the services layer's plugin adds the text as a "datapath" section to the report of a test that failed in its call and has an `Online` among its fixtures (`item.funcargs`, which holds the fixture closure's values). The section comes from the same layer as the fixture, so the harness's other layers do not learn of the datapath.

### D4. The tests

`testing/harness`, in `tests/testing/test_harness.py`:
- "A reboot that does not come": the router detaches a command that prints a marker and ends; `wait_rebooted()` with a short limit raises `TimeoutError`, whose notes hold the command, the marker and the console's text.
- "A failing test with the router online": the hook gets a stand-in item whose fixtures hold the module's `Online`, and a failed call report; the report it returns has a "datapath" section that holds the clients' routes, the router's `ifstatus wan` and the ISP's sessions. A passing report gets no section.

### D5. Verification

- The tests pass on both boards.
- A deliberately failing online test and a deliberately missing reboot on the VM: their reports, read, name what D2 and D3 say.
- CI with snapshot-return, on the same branch.

## Risks / Trade-offs

- [Gathering hangs on a router that does not answer] → Every command has the harness's own time limit, and the parts are read one by one.
- [Larger failure reports] → Only failing tests get them; the datapath section is a few hundred lines at most.
