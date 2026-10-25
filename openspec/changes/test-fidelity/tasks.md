# Tasks

## 1. The tests of the new scenarios (design D14)

- [x] 1.1 Add the tests of the change's scenarios in `tests/testing` (D14).

  Verify: `just check` passes; `spec-coverage --change test-fidelity` reports every scenario covered.

## 2. The harness (design D9 to D13)

- [x] 2.1 Commands and login sessions end with their time limit (D9).

  Verify: the testing/harness tests pass on both boards.
- [x] 2.2 The report asks first whether the router answers (D10).

  Verify: the testing/harness tests pass on both boards.
- [x] 2.3 WireGuard's setup and the write throttle undo what they did (D11).

  Verify: the testing/harness, services/vpn and firmware/ab-upgrade tests pass on both boards.
- [x] 2.4 The console's end (D12); the netprobe unit tests' waits (D13); a module's router (D16); the disks through a power cut (D17).

  Verify: the testing/emulation and unit tests pass.

## 3. Faithful tests (design D1 to D8)

- [x] 3.1 netprobe's SYN MSS and the MSS test (D1), the offload test (D2), inbound IPv6 refused (D5).

  Verify: the network/wan tests pass on both boards; on the VM, without the router's MSS clamp, the MSS test fails.
  Done 2026-10-27: without the wan zone's `mtu_fix`, the client's SYN reached the server with MSS 1460 on both boards, above the test's 1452.
- [x] 3.2 The spoofed frame at the WAN port (D3), the ICMP count (D4).

  Verify: the network/nat and network/tc-hook-order tests pass on both boards; on the VM, the frame sent to a LAN port's MAC fails the spoofed-frame test.
  Done 2026-10-27: a frame to the LAN port's MAC reached the WAN port 0 times on both boards (R6S: eth0, the old test's), which fails the test's check that it did.
- [x] 3.3 The reload's pings (D6), the restarted declaration (D7), the pulled disk (D8), the health check limits of a test's own run (D18).

  Verify: the network/transparent-proxy, services/containers and storage/data-disk tests pass on both boards.

## 4. Integration

- [x] 4.1 Run every suite on both boards.

  Verify: no failure; the suites' durations recorded beside the previous runs'.
  Done 2026-10-26/27 on the VM: every suite passed on both boards. Minutes, R4S: upgrade 44, boot 32, system 20, network 17, services 27, release 45 (the morning's run on the same VM: 44, 33, 20, 19, 26, 38); R6S: 40, 30, 18, 13, 25, 37.
- [ ] 4.2 Get a green CI run for both boards.

  Verify: record the run in `docs/ci.md`.

## Workflow follow-up

- Sync the delta specs, archive the change, merge it to main and push Codeberg first, then GitHub.
