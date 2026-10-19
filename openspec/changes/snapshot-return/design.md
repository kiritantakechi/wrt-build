# Design

## Context

See proposal.md for why. The current state:
- `Router.reset()` disconnects, has the emulator `loadvm` its post-boot snapshot, and calls `set_clock()`, which runs `date -s @<the runner's time>` over SSH. labgrid's SSH driver connects on the first command after a disconnect; the runner's time is taken before it.
- The tests run in the runner's own network namespace on the LAN segment of the router's first LAN port, where the router is 10.0.0.1. The LAN clients have namespaces of their own.
- In failsafe mode, preinit puts 10.0.0.1 on the first LAN port with the port's hardware MAC address (`52:54:00:0a:00:10` in the emulator). The normal system puts it on `br-lan`, with the MAC address the board's configuration gives both LAN ports on the R6S (`86:03:2a:9e:24:a7`). The R4S's single LAN port keeps its address.
- After `loadvm`, the runner's neighbour entry for 10.0.0.1 still names the failsafe MAC address, reachable; the restored system announces nothing. Measured on the VM: the first command after the return took 36.1 s after failsafe mode and 0.4 s without; the router's clock was 36.3 s and 1.2 s behind the runner's.
- The upgrade image is signed at its first use in a run (`signed_repo`, `scripts/release-sign.sh`); its `ucert` certificate is valid from then on. `fwtool_check_signature` on the router runs `ucert -V`, which refuses a certificate the router's clock has not reached without a message.

## Goals / Non-Goals

**Goals:**
- The router at its snapshot again reaches the runner at once, after any test.
- The router's clock is the runner's, checked, after every return to the snapshot.

**Non-Goals:**
- The LAN clients' own neighbour entries: they do not talk to a router in failsafe mode, which runs no DHCP or router advertisements, and a test that brings the router online has them announce themselves anew (`Online.dial`).
- Signing earlier or with a certificate valid from before now: a release's certificate is valid from its signing, and the router must not accept less.

## Decisions

### D1. The runner forgets the router's link-layer address after the return

`Router.reset()`, after `loadvm`, removes the runner's neighbour entry for the router's address (`ip neigh flush to <address>`), as a host's entries go when its link goes down and up with a restarted router. The harness changed the machine under the link, so the harness discards what it learned since; the next connection resolves the address anew.

Alternatives considered:
- **The restored router announces itself** (a gratuitous ARP from the router): it would need a command channel before SSH works, the serial console, and a tool on the router for a fault of the harness.
- **A shorter reachable time for the runner's neighbour entries**: it would shorten the wait, not remove it, and leave the cause.

### D2. `set_clock()` steps the clock by a measured offset, and checks it

`set_clock()` reads the router's clock (`date +%s.%N`) and compares the reading with the middle of its round trip on the runner, as NTP measures an offset: the router read its clock somewhere within the trip, so the offset is as precise as half of it. Of up to five readings, the first whose round trip is at most a second counts, else the quickest; the first reading also makes the connection, however long that takes. The router then steps its own clock by that offset (`date -s @$(date +%s.%N | awk ...)`, rounded to the whole second `date -s` sets), so the time the command takes to arrive does not count. A second reading checks the result: an offset larger than a second plus half of both readings' round trips fails the call, naming the skew. The second covers the rounding to whole seconds and the emulated clock's own drift, over a percent slow under TCG, between the readings. A slow connection or a loaded runner then cannot skew the clock, and a skew from any other cause is named where it arises, not as a refused signature later.

First measured on the VM, setting the runner's time sent in the command (`date -s @<time>`) left the router 2 to 7 s behind under the Mac's load, as long as the command took to arrive; a fixed two-second check then failed returns that were correct.

Alternatives considered:
- **A time server in the emulated internet**: the router's `ntpd` would step the clock only after its first exchanges, later than the tests need it.
- **The runner's time sent in the command, with a fixed tolerance**: the command's travel time is the error, and under load it exceeds any tolerance tight enough to matter.

### D3. The test

`testing/emulation` "Back from failsafe mode", in `tests/testing/test_emulation.py`: the router reboots into failsafe mode as firmware/base-system's test does it (`f` at the console prompt), then `router.reset()` returns it to its snapshot. The test requires the return to take less than 25 s, where a stale link-layer address costs more than 30 s on top (the return took 69 s without the fix, and 16 s with it on four host cores that `stress-ng` slows as CI's slow runners), and the router's clock afterwards within two seconds of the runner's.

### D4. Verification

- The test fails without D1 and D2 on the R6S, and passes with them on both boards.
- CI's R6S image in CI's order (the first three tests of `firmware/test_base_system.py`), three sessions: all pass.
- The testing and firmware suites on both boards; CI, with ci-system-split's order of tests.

## Risks / Trade-offs

- [The clock check fails a run on a router whose clock cannot be set] → That run's signed images would have failed anyway, later and without a word; the check names it.
- [Flushing an entry that another process of the runner uses at the time] → The tests are the runner's only users of the router's address, and the return disconnects them first.
