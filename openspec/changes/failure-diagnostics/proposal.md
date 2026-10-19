# Proposal

## Why

Two failures in CI this month ended in messages that did not say why, and each took a day on the VM to explain:

- `test_upgrade_keeps_the_lan_address`: "the router never rebooted". The harness starts `sysupgrade` detached with its output to `/dev/null`, so its "Image check failed." was lost; reproducing it with the output kept found the cause (snapshot-return).
- `test_lan_host_gets_ipv6` (run 38638989005): "Network is unreachable" from client-a, whose IPv6 default route had gone although the online fixture required one. Nothing recorded the router's WAN state, its log or the emulated ISP's view at the failure. On the VM, eight full network suites and 24 targeted attempts, under load and without, did not reproduce it; a freeze of the emulator of 20 s or more does (the ISP's pppd hangs up a peer that does not answer three echo requests, and the clients lose their default route while the router dials again), but CI's run shows no such freeze before its failure, so its cause stays open.

A harness that names what it can still see at a failure turns the next such failure into its own explanation.

## What Changes

- **A command the harness detaches on the router keeps its output**, in a file on the router that the reboot it leads to clears.
- **A wait for a reboot that does not come shows** the command that was to reboot the router, its output, read from the system that ran it, and the console since the command ran.
- **A failing test with the router online gets a report section on the datapath**: the LAN clients' addresses and routes, the router's WAN and WAN6 state with its PPP and router-advertisement log, and the ISP's sessions with the end of its pppd log.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `testing/harness`: failures name the router's state.

## Impact

- `tests/wrt_tests/device/router.py`: `detach()` and `wait_rebooted()`.
- `tests/wrt_tests/services/datapath.py`, `services/fixtures.py`: the datapath's state, and the hook that adds it to a failing test's report; `sandbox/isp.py`: the ISP's log.
- `tests/testing/test_harness.py`: the tests.
- No change to the firmware, the build or a test's outcome; only failure reports grow.
