# Design

## Context

See proposal.md for why. The current state:
- `wrt_tests.model.poll.until(probe, *, timeout, what, every=1)` is how every test and harness module waits. It calls the probe until the answer is neither `None` nor `False`, returns that answer, and raises `TimeoutError` naming `what` when the time is up.
- 56 calls pass a probe. Most answer with a comparison, so a `bool`. Others answer with a value or `None`: a session, a dict of what a probe saw, the mount options as a set. Six answer with a value that is empty while the condition does not hold:
  - `client.run("ss", ...)`, the empty output of `ss` while nothing listens: the netprobe server in `tests/network/test_wan.py` and the UDP listener in `tests/network/test_nat.py`;
  - the conntrack lines of the offloaded flow, an empty list before the flow is offloaded (`tests/network/test_wan.py`);
  - netifd's `ipv6-prefix` of wan6, a list that is empty before the ISP delegates the prefix (`Online.wait_datapath`);
  - `router.run(command) or None` (`wrt_tests.device.storage`) and `client.run(...) or None` (`tests/testing/test_emulation.py`), which turn the empty output into `None` themselves.
- The reproduction: `network/test_wan.py` ten times on the R4S on the VM, with `stress-ng --cpu 4` beside the emulator and `tcpdump` on the sandbox's `br-lan`: three runs failed, each with client-a resetting client-b's SYN within 5 µs, and the server listening right after.

## Goals / Non-Goals

**Goals:**
- One contract for waiting that an empty answer cannot pass by accident, whatever the probe returns.

**Non-Goals:**
- Waits that do not go through the helper: shell loops on the router (`until logread ...; do sleep 2; done`) and labgrid's own.
- Changing any probe's condition or time limit.

## Decisions

### D1. An empty answer is no answer: Python's truth testing

`until` waits while `not probe()`, and returns the first answer that is true in Python's sense.
- That is how `if` and `while` read a value, so a probe means what it would mean in a condition: `ss`'s output, a list of matches or a prefix list is "there" once it has content.
- Every answer that ended a wait so far still does: a `True` comparison, and every value, which has content when the condition holds (a session, a dict, a non-empty set, a page).
- `None` and `False` stay no answer, as before.

Alternatives considered:
- **Keep `None` or `False`, and fix the six probes** (`or None`, `!= ""`): the trap stays for the next probe, and it caught four of the six.
- **A sentinel for "not yet"**: every probe would have to return it, and an empty answer would still pass by accident.

### D2. The workarounds go

`router.run(command) or None` and `client.run(...) or None` become `router.run(command)` and `client.run(...)`: under D1 they mean the same, and leaving them would suggest the helper still needs them.

### D3. Tests

The two scenarios of `testing/harness` ("Waiting for a condition") in `tests/testing/test_harness.py`, with a probe that answers from a list of prepared answers and `every=0`:
- empty string, then empty list, then a value: `until` returns the value after three calls;
- only empty answers: `TimeoutError`, whose message names `what`.

### D4. Verification

- The reproduction of the Context, before and after the change: three of ten failed before (2026-10-14); after, ten of ten must pass.
- The full system tests on both boards, then CI: a wait that used to end at once now lasts as long as its condition takes, within its time limit.

## Risks / Trade-offs

- [A wait that passed by accident now finds its condition never holds] → It fails with what it waited for, which is a real failure the old contract hid; the full suites and CI show any. It is investigated, not relaxed.
- [A future probe that wants to report an empty value as its result] → It returns something with content (a tuple, a dataclass) or a comparison; the docstring says so.
