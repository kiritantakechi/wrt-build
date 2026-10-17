# Proposal

## Why

The A/B tests fail now and then in CI's `system` jobs: the router resets without a message during an upgrade test and comes back on the wrong slot or its first boot's state (runs 37293958173 and 38252151081, and main's run 38696888543, where `qemu.log` named the emulator's watchdog). On the VM, the A/B modules on four host cores that `stress-ng` slows, as a slow runner is, reset that way seven to nine times a run; on four unloaded cores, never.

A monitor in the guest found the cause in all seven resets of such a run: procd sat in `anon_pipe_read` for the last 22 to 28 s before each, while the rest of the guest ran on. procd's `system` object validates an upgrade image (`validate_firmware_image`, and `sysupgrade` before it starts the upgrade) by running `/usr/libexec/validate_firmware_image` and reading its output in its main loop until the script ends. Meanwhile procd feeds no watchdog, answers no ubus call and supervises no service. On a slow host the validation of an upgrade image takes longer than procd's 30 s watchdog timeout, and the watchdog resets the router before the upgrade begins. A device whose validation takes as long, a slow one with a large image, resets the same way. Upstream procd validates the same way today.

This change replaces emulator-watchdog-time, whose premise, an emulator that starves the guest, the measurements disproved: the guest's cores ran throughout, and procd itself stopped feeding the watchdog.

## What Changes

- **procd validates upgrade images without blocking its main loop.** A procd patch (meant for upstream, `Upstream-Status: Pending`) reads the validation script's output as it comes, in procd's event loop, and answers the request once the output is complete: `validate_firmware_image` replies then, and `sysupgrade` goes on to the upgrade then. Each validation keeps its own result and error, so two at once do not mix.
- **A test that validates an image slower than the watchdog's timeout.** The image is a FIFO that nobody writes for 45 s, so every read of it waits, on any host. The router must not reset, procd must answer other calls meanwhile, and the validation must end with its result once the image's reads return.
- **emulator-watchdog-time goes.** Its proposal leaves `openspec/changes`; the starvation test it added never reached main.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `firmware/ab-upgrade`: the system keeps feeding its watchdog and answering requests while it validates an upgrade image, however long the validation takes.

## Impact

- `patches/openwrt`: a new patch adding procd's `patches/` with the source patch, `PKG_RELEASE` 3; `docs/patches.md`: its write-up.
- `tests/firmware/test_ab_upgrade.py`: the slow validation test.
- The firmware of both boards: procd.
