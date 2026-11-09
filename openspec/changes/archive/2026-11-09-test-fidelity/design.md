# Design

## Context

See proposal.md for why. The mechanisms the fixes depend on, as read in their source:
- Linux: `TCP_MAXSEG` on a connected socket is the MSS the stack sends with, the peer's advertised MSS less the TCP options of every segment (12 bytes with timestamps). `TCP_SAVE_SYN` (27) on a listening socket keeps each SYN's headers, which `TCP_SAVED_SYN` (28) returns on the accepted socket.
- fw4: the wan zone's `REJECT` answers a TCP SYN with a reset.
- dropbear: the process of a connection calls `setsid()` once; the commands of all its channels run in that session, in one process group.
- labgrid's `SSHDriver.run()` waits with `communicate(timeout=...)`, which raises without ending ssh, so the command goes on running on the router. `QEMUDriver._read()` returns an empty read for every select once QEMU has closed the console's socket; `off()` asks QEMU's monitor to quit, which fails once QEMU has exited. The SSH driver's connection timeout is 120 s (`tests/wrt_tests/device/emu.py`). `QEMUDriver.on()` starts a new QEMU, stopped (`-S`), restores the port forwards labgrid made, and lets it run: devices added through the monitor are not restored.
- BusyBox 1.38 in the image has `setsid`, `flock` and `timeout`; its `timeout` ends only the program it runs, not the processes that program started.
- `wrt-containers start` runs `wrt-containers apply` as a procd instance: the Pods start after the init script returns.

## Goals / Non-Goals

**Goals:**
- Every test the audit found vacuous fails without the behaviour its scenario names; every harness defect fixed where it lies.

**Non-Goals:**
- A watchdog on the router for commands whose harness side is gone: a command's time limit is enforced by the harness that waits for it (D9).
- Tailscale's setup: `Tailnet.join` clears the tailnet and logs both ends in again every time, so a failed join leaves nothing a later one trips on.
- Killing the local ssh of a command that timed out: it ends when the router's side does.

## Decisions

### D1. The MSS the peer receives
netprobe's server sets `TCP_SAVE_SYN` on its listening sockets and reports, for each connection, the MSS option of the SYN as it arrived (`TCP_SAVED_SYN`, parsed from the network and TCP headers). The MSS test then sees the clamp itself: 1452 through the router, 1460 without it. The netprobe unit test expects the SYN's MSS of its own path exactly: 1460 over IPv4, 1440 over IPv6.

### D2. The offloaded flow's own packets
The download runs 60 s and the test waits at most 20 s for its flow to show `[OFFLOAD]`. Then, at the iperf3 server on the emulated internet (`ss -ti`), every connection of the download has the WAN address as its peer (iperf3 listens on both families, so ss shows an IPv4 peer mapped into IPv6, which the test reads as IPv4), and the segments it received grow while conntrack shows the flow offloaded before and after. A flowtable that passed the flow's packets on untranslated would deliver them from the LAN address, which no server socket takes, and the count would stand still.

### D3. The spoofed frame reaches the WAN port
The frame goes to the MAC of the board's WAN device (`board.wan.device`). A table of the test's own counts the IPv4 frames that device's ingress sees (netdev family), so the test shows they arrived; it is removed afterwards.

### D4. The ICMP count told apart from the background
200 pings at 10 ms. Before them, the test counts qosify's runs over a quiet window as long as the pings take, and requires fewer than a quarter of the pings there, so that the measurement can tell: the WAN's background makes a few packets a second (11 in a first design's 4 s window of 20 pings, which could not tell). The pings' window must then grow by at least one run per reply received.

### D5. Inbound IPv6 is refused
The internet's probe is `connect`, whose answer must be `refused`: a timeout no longer passes.

### D6. The pings span the reload
The pings have no count. They start before the write and end, by SIGINT, once the saved configuration is in effect; nsenter runs ping in its own process, so the signal reaches it, and ping prints its summary on it. No ping of the whole reload may be lost.

### D7. Restarted, not rebuilt
The test reads the container's start time, restarts the service, waits until the start time changed (the startup flow ran: the stop and the start), then requires the same container ID.

### D8. A pulled disk is gone first
`removed(router, disk)` waits until no block device has the disk's model; the spare-disk test calls it after pulling the disk out, before plugging it in again.

### D9. Commands end with their time limit
- `Router` runs each command as `echo $$ >/tmp/wrt-tests.pid; exec setsid sh -c '<command>'`: the shell, in a session of its own, keeps its PID, which the file records. dropbear's one session per connection would otherwise hold every command of the connection in one process group.
- When labgrid's wait times out, the harness kills that session's process group over the connection (`kill -KILL -- -<pid>`), and raises `TimeoutError` naming the command and its limit. The harness runs one command on a router at a time, so one file suffices.
- A login session's output is read by a thread while the harness waits for it; at the time limit the harness kills the session's ssh, whose pseudo-terminal then hangs up the shell on the router, and raises `TimeoutError` with what the session printed. Reading meanwhile also keeps a long output from filling the pipe and stalling the session.

### D10. A report that finds out first
`Router.reachable()` opens a fresh connection with a 5 s connect timeout and runs `true`. A failure's report asks it once before the router's parts: a router that does not answer is one part saying so, and the LAN clients' and the ISP's parts are read as before.

### D11. What a test sets up, it takes down
- `WireGuard.connect()` removes the peer's tunnel when anything after its creation fails, and raises the failure.
- `Emulator.throttled_writes(bps)` is a context manager. On exit it lifts the limit, unless the machine was powered off meanwhile, which ended the QEMU that held it. The power-loss test uses it.

### D12. The console's end
`Console` reads through a function the emulator gives it, labgrid's `_read`. An empty read means QEMU closed the console; the reader records that the console ended, stops and wakes every waiter. Any other error is recorded as the reason the console cannot be read. `wait_for` raises `ConsoleEndedError` with the reason at once. Starting the machine again starts a fresh reader.

### D13. Waits with a time limit
The netprobe unit tests wait for their servers with `until` and a time limit.

### D16. A module's router is the module's
A module's fixtures that keep the router (`module_router`, and through it `online` and what builds on it) dial in or start Pods once for the module. A function-scoped `router` returns the router to its snapshot after its test, which takes that state from the module's later tests: they then fail for that alone, as the WireGuard test of this change did. `module_router` marks the router as held by its module while it lives, and `router` fails at its setup on a held router, naming the module. A module puts its tests that reset the router first, as `network/test_wan.py` already does.

### D17. A power cut leaves the disks plugged in
`Emulator` records each disk `plug_disk()` plugs in, with its image and port, until `unplug_disk()` pulls it out. `power_on()` plugs the recorded disks in again once QEMU runs, during the firmware, so the kernel finds them as it finds a disk plugged in at power-on; a disk that came later would be a hot-plug, which the system handles alike, so nothing depends on the moment.

### D18. A test's health check limits end with its run
The health check tests set the check's limits with `uci set` and run it, without `uci commit`: the health check reads the changes the uci delta keeps in `/tmp/.uci`, which a reboot clears, so the boot a test reboots into checks with the image's limits. The rollback test and the upgrade drill commit theirs on purpose: the boots after them are to fail quickly.

### D14. Tests
- testing/harness:
  - "A failing test with the router unreachable": a table of the test's own drops new connections to the router's SSH port, the report is built and timed, and the table goes over the connection already open;
  - "A command that overruns its time limit": `flock` holds a lock in a process of the command's, the command runs past 3 s, and the lock is then free;
  - "A login session that does not end": a login that prints and sleeps fails at 5 s with what it printed;
  - "A setup that fails halfway": `WireGuard.connect()` with a route the peer refuses, then with valid ones;
  - "A test that fails while writes are slowed": QEMU's block info shows no write limit after a failure inside `throttled_writes`;
  - "A test that would reset a module's router": the guard on a router a module holds, and on one it does not.
- testing/emulation, "QEMU exits while a test waits for the console": the console reads with labgrid's `_read` over a socket pair, and the far end closes as QEMU's does when it exits.
- testing/emulation, "Power cut with a disk plugged in": a disk plugged in before a power cut is the router's block device after it.
- The fixed tests of `network/wan`, `network/nat`, `network/tc-hook-order`, `network/transparent-proxy`, `services/containers` and `storage/data-disk` run on both boards. A change that breaks what each checks, made on the VM, makes it fail: the clamp's rule removed, the frame to a LAN port's MAC, the ICMP replies passed by einat. Where such a run is too costly, the reason is recorded.

## Risks / Trade-offs

- [`setsid` per command] → One more exec per command on the router, some milliseconds under the emulator; the suites' durations are compared before and after.
- [The quiet window of D4 may see a burst] → Then the test fails saying the window was not quiet, rather than pass on the burst.
- [Dropping new SSH connections in a test] → The table goes over the connection that is already open; the module's router is restored by its snapshot in any case.
