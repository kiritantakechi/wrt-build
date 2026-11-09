# Proposal

## Why

The audit of 2026-10-26 also read the test harness and the tests. Each finding below was checked against the code and, where it depends on another component, against that component's source:

- **Tests that pass without testing:**
  - The MSS test reads the server's `TCP_MAXSEG`, the effective MSS less the TCP options. An unclamped 1460 then shows as 1448, below the 1452 the test allows.
  - The offload test finds the iperf3 flow offloaded, then checks the source address of three new, short connections, which are never offloaded; and it waits for the offload exactly as long as the download lasts.
  - The spoofed-frame test sends to the MAC of `eth0`, which is a LAN port on the R6S: the WAN port never takes the frame, and the test passes on that board whatever the firewall does.
  - The ICMP test of the tc hook order counts three runs of qosify, which the WAN's background traffic alone can make.
  - The inbound IPv6 test accepts any failure, a timeout included, where the spec asks for a rejection.
  - The LuCI reload test pings for 10 s, while the reload it covers may take up to 120 s.
- **Tests that fail for the harness's sake:**
  - The unchanged-declaration test expects the Pod stopped right after the restart, which starts it again asynchronously.
  - The spare-disk test may look up the block device of the disk it has just pulled out.
  - The test of a failing trial boot commits the health check's 6 s limits, so the boot it reboots into, which must pass and confirm the slot, gets 6 s too; on a slow runner it fails and reboots again (CI run 40281789469).
- **The harness:**
  - A command that runs past its time limit goes on running on the router: labgrid gives up on ssh without ending it. One that holds a lock, as `wrt-sync` does, fails the module's later tests.
  - A login session that does not end makes the harness wait for it forever.
  - The report of a failed test with the router down waits 120 s for each of three connections, so that a suite of such failures runs past its job's time limit.
  - The WireGuard peer's tunnel stays in the session's namespace when it fails to come up, and every later module that wants one fails.
  - A failure before the power cut leaves the boot disk's writes throttled for the session.
  - The console's reader turns in a loop once QEMU has exited, and dies silently on any other error, so that every wait on the console runs out its time limit.
  - Two waits of the netprobe unit tests have no time limit.
  - A forced power cut pulls out every disk a test plugged in: QEMU starts anew without them, so that a test of what a power cut leaves finds no data disk.

## What Changes

- **Faithful tests:** netprobe reports the MSS of the SYN as the server received it; the offload test checks the offloaded flow's own packets at the server while it is offloaded; the spoofed frame goes to the board's WAN port, which is shown to receive it; the ICMP count is told apart from the background; the inbound connection must be refused; the pings run until the new configuration is in effect.
- **Race-free tests:** the unchanged declaration is shown restarted by its start time, not by a moment without it; a disk pulled out is waited for until its block device is gone; the health check tests' short limits hold for the run that sets them, not for the boot after it.
- **The harness:**
  - A command past its time limit is ended on the router, with every process it started, and fails as a timeout that names it.
  - A login session past its time limit is ended and fails with what it printed.
  - A failure's report finds out first, within seconds, whether the router answers at all.
  - The WireGuard peer's setup undoes what it did when it fails; the write throttle is lifted when its test ends, however it ends.
  - The console's reader notices that the console ended or failed, and every wait on it fails at once, saying so.
  - Every wait of the tests has a time limit.
  - A disk stays plugged in through a power cut.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `testing/harness`: commands and login sessions on the router end with their time limit; what a test sets up it takes down, also after a failed setup; a failure's report of an unreachable router is quick.
- `testing/emulation`: a wait on the console fails at once when the console ended; a disk stays plugged in through a power cut.

The tests of `network/wan`, `network/nat`, `network/tc-hook-order`, `network/transparent-proxy`, `services/containers` and `storage/data-disk` change, but none of their scenarios does: the tests now check what the scenarios already say.

## Impact

- `tests/wrt_tests/device/router.py`, `emu.py`, `storage.py`; `tests/wrt_tests/services/datapath.py`, `vpn.py`, `tests/services/conftest.py`; `tests/wrt_tests/sandbox/netprobe.py`.
- The tests named above, `tests/firmware/test_ab_upgrade.py`, `tests/unit/test_netprobe.py`, and the new scenarios' tests in `tests/testing`.
