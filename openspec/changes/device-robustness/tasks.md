# Tasks

## 1. SMB shares withdrawn on unmount (design D1, D2, D3)

- [x] 1.1 Write the procd patch (D1): `_procd_add_mount_event_trigger`, the unmount helpers and their exports, and `_procd_add_mount_trigger` naming the script from `$initscript`. Carry it under the next free openwrt patch number with `Upstream-Status: Pending`, and its write-up in `docs/patches.md`.

  Verify: `just patch` applies it. For each present user (log, ksmbd-tools, transmission, nfsd v3 and v4, postgresql), the trigger JSON its `service_triggers` produces with one mount point is the same before and after, as a script that sources `procd.sh` on the host shows. Two mount points produce one `or` condition with both.
- [x] 1.2 Write the fstools patch (D2): `mount_action("remove")` unmounts before the hotplug removal, and blockd's `umount` handler reports only a target it knows. Carry it under the next free number with `Upstream-Status: Pending` and its write-up.

  Verify: fstools builds for both boards. On the router, `echo remove` to the data disk's `uevent` produces a `mount.remove` with `"target": "/mnt/data"`, as `ubus subscribe block` shows.
- [x] 1.3 Revise packages patch 0001 (D3): reload triggers per share for the mount and the unmount, and a running server stopped before a start with nothing to share returns. Update its message, `PKG_RELEASE` and its write-up in `docs/patches.md` (the gap it states is closed).

  Verify: `just patch` applies the series. The services/file-sharing test "Data disk removed while sharing" (new, D6) passes on both boards, and so does "Data disk absent".

- [x] 1.4 Add wrt-data's preinit hook (D7) that puts the mount point on a small tmpfs, bump wrt-data's `PKG_RELEASE`, and add the storage/data-disk test "Data disk removed while in use" (new).

  Verify: on both boards the new test passes, the file-sharing test "Data disk removed while sharing" finds nothing on the boot disk under `/mnt/data`, and the storage/data-disk, services and firmware/ab-upgrade suites pass.

## 2. podman's database check at any concurrency (design D4)

- [x] 2.1 Before the fix, add the services/containers test "Runtime commands at the same time" (D6), and run it on the current image to record how often a round fails.

  Verify: the failure rate is noted in the patch's write-up as the reproduction.
- [x] 2.2 Write the podman patch (D4) for SQLite and BoltDB states, as a new packages patch with `Upstream-Status: Pending` and its write-up, and bump the podman package's `PKG_RELEASE`.

  Verify: podman builds for both boards with no UB-indicative warning that `tests/reviewed-warnings.toml` does not review. The test of 2.1 passes on both boards, and so do the services/containers and release/device-sync suites.

## 3. qosify's ifb names (design D5)

- [x] 3.1 Write qosify patch 104 (the ifb name's tail, `ifb` in the status) and the `qosify-status` change, carried by a new openwrt patch with `Upstream-Status: Pending` and its write-up; bump qosify's `PKG_RELEASE`.

  Verify: qosify builds for both boards. The network/qos test "Ingress shaping on a device with a long name" (new, D6) passes on both boards, and so does "Enable ingress shaping".

## 4. Integration

- [x] 4.1 Run the full system tests on both boards (dev profile).

  Verify: all tests pass on both boards, and `spec-coverage --change device-robustness` reports no uncovered scenario.
- [ ] 4.2 Get a green CI run for both boards.

  Verify: record the run and its per-board timings in `docs/ci.md`.

## Workflow follow-up

- Sync the delta specs, archive the change, merge it to main and push Codeberg first, then GitHub; then apply build-integrity.
