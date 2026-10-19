# Proposal

## Why

ci-system-split's two CI runs (39120617912 and 39177086857) failed the R6S's `system` job in the same test, `firmware/test_base_system.py::test_upgrade_keeps_the_lan_address`: the router "never rebooted" after `sysupgrade`. On the VM, CI's own R6S image in CI's order of tests failed it in five sessions out of five. Traced, the chain is:

- The test before it boots the router into failsafe mode, where preinit puts the LAN address on the first LAN port with that port's own MAC address. The normal system has it on `br-lan`, whose MAC address the R6S's board configuration sets for both LAN ports. The R4S keeps one MAC address in both modes.
- The harness then returns the router to its post-boot snapshot. Nothing on the link changes at that, so the runner's neighbour entry still names the failsafe MAC address, reachable, and the runner's first SSH connection waits until the entry is resolved again: 36 s, where it takes 0.4 s after a test without failsafe mode.
- `set_clock()` takes the runner's time before that connection, so the router's clock is set 36 s behind the runner's (measured: 36.3 s after failsafe mode, 1.2 s without).
- The test is the first of the run to ask for the signed upgrade image, so the image is signed then, by the runner's clock. Its certificate is valid from that moment, which the router's clock has not reached: `ucert` refuses the signature without a message, `sysupgrade` stops with "Image check failed.", and the router never reboots. Two minutes later the same image validates.

Before the split, the A/B tests asked for the image first, long before, which hid the skew.

## What Changes

- **The runner forgets the router's link-layer address when the snapshot comes back.** The restored router is another state of the machine; what the runner learned of it since the snapshot no longer holds. Its first connection then resolves the address anew.
- **`set_clock()` sets the time when the command runs, and checks it.** It connects first, sets the runner's time, reads the router's clock back and fails, naming the skew, if the two differ by more than two seconds.
- **A test returns the router from failsafe mode to its snapshot** and requires a prompt answer and the runner's time.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `testing/emulation`: the router back at its snapshot answers at once, with the runner's time.

## Impact

- `tests/wrt_tests/device/router.py`: `reset()` and `set_clock()`.
- `tests/testing/test_emulation.py`: the new test.
- No change to the firmware or the build.
