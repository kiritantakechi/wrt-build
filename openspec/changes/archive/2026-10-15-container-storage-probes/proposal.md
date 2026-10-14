# Proposal

## Why

The services/containers test "Runtime commands at the same time" failed in both attempts of harness-polling's CI run 38556156281 on the R4S. Its cleanup could not remove the scratch storage: `.../overlay/compatNNN/lower-mapped` and `merged` were still mounted (`Resource busy`). Nothing in the change touched containers; four earlier runs and the local suites passed.

The mounts are podman's own. Its storage's overlay driver probes some kernel features when it is first asked about them: idmapped lower layers in `podman info` and in every layer or container creation, volatile mounts in `podman info`. Each probe mounts in a directory under the driver's home and unmounts by path. Meanwhile another podman process may bind the home onto itself, as every command does when it starts and finds the home unmounted after an earlier one's end. The bind hides the probe's mounts from the paths it unmounts them by: podman warns `Unmount ".../compatNNN/lower-mapped": invalid argument`, and the mounts stay until a reboot. The store's graph lock keeps the bind apart from the probes that the driver's initialization makes, but not from the later ones.

On the R4S on the VM, with the probes' records removed as they appeared, the test reproduced it: two of ten rounds left the probes' idmapped and volatile mounts behind. On a router, the storage is on the data disk, and wrt-containers and wrt-sync run podman at once after a boot, when the run root in RAM has no record of the probes yet. A mount left under the storage keeps the data disk's mount busy until a reboot.

## What Changes

- **The storage's probes leave nothing mounted.** A podman patch (for go.podman.io/storage, which podman vendors) gives the overlay driver a lock of its own for its home's mount. The driver holds it while it binds the home, while it unmounts the home at a command's end, and while a probe that runs after the initialization mounts under the home. The patch is meant for upstream (`Upstream-Status: Pending`), with its write-up in `docs/patches.md`.
- **The concurrency test shows what it finds.** Each round reports podman's errors and what is left mounted under the scratch storage, and the test fails naming the first round that left anything. Its cleanup unmounts what a round left, and never raises in place of the result. The probes' records are removed as they appear, so every command probes, and each of the commands started at once runs several in a row, so binds, unmounts and probes keep overlapping through a round.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `services/containers`: container runtime commands that run at the same time leave nothing mounted under the container storage once they have ended.

## Impact

- `patches/packages`: a new podman patch, `PKG_RELEASE` 5; `docs/patches.md`: its write-up.
- `tests/services/test_containers.py`: the concurrency test.
- The firmware of both boards: podman. Its probes now wait for a bind or an unmount of the storage's home by another podman command, which is quick, and run once per boot.
