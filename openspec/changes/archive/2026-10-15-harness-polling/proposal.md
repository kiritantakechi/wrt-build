# Proposal

## Why

`tests/network/test_wan.py::test_inbound_ipv6_is_rejected` fails now and then in CI: client-b's TCP probe to client-a's global IPv6 address is refused while client-a's netprobe server listens (main's run 38102368454 on the R6S, device-robustness's run 38252151081 on the R4S). The test waits for the server with `until(lambda: client.run("ss", ...))`, and the harness's polling helper `until` stops on any answer but `None` or `False`. `ss` prints nothing while no socket listens, and `run` returns that empty string, so the wait ends at once and the probe races the server's start.

On the VM, with the test module run ten times under CPU load, three runs failed this way. A capture on the sandbox's LAN bridge showed client-b's SYN reaching client-a's own MAC address and client-a's reset 4 µs later; the server listened on `[::]:8007` only after that. The same contract lets other waits pass at once: the NAT test's wait for its listener, the WAN test's wait for an offloaded flow, and the online fixture's wait for the delegated prefix, whose answer is a list that may be empty.

## What Changes

- **The polling helper waits for an answer with content.** `until` treats an empty answer as no answer yet: `None`, `False`, zero, an empty string and an empty collection alike, as Python's truth testing does. It returns the first answer with content, and fails naming what it waited for once the time is up.
- **The waits that ended early wait.** The probes stay as they are; the helper's contract fixes them: the netprobe server's and the NAT listener's start, the offloaded flow, and the delegated prefix.
- **The workarounds go.** Probes that turned an empty answer into `None` themselves (`or None`) no longer need to.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `testing/harness`: the harness's polling helper keeps waiting while a probe's answer is empty.

## Impact

- `tests/wrt_tests/model/poll.py`: the helper's contract.
- `tests/wrt_tests/device/storage.py`, `tests/testing/test_emulation.py`: the `or None` workarounds go.
- `tests/testing/test_harness.py`: the scenarios' tests.
- No change to the firmware or the build. Waits that ended early now take as long as their condition does, within their existing time limits.
