# Tasks

## 1. The tests (design D10)

- [x] 1.1 Add the tests of every new scenario of the change, in the modules of their capabilities (D10).

  Verify: `just check` passes; `spec-coverage --change device-integrity` reports every scenario covered.

## 2. The A/B code (design D1, D2)

- [x] 2.1 `wrt.ab`'s `variables()`, the health check's environment and confirmation, and `wrt-slot status` (D1).

  Verify: the firmware/health-check tests pass on both boards.
- [x] 2.2 The upgrade hook: members read whole, checked writes, the configuration before the switch (D2).

  Verify: the firmware/ab-upgrade tests pass on both boards.

## 3. The sync (design D3)

- [x] 3.1 The tag checks, the package archive's listing, the release built from its verified parts, the flushes, and `wrt-update`'s image (D3).

  Verify: the release/device-sync tests pass on both boards.

## 4. The services (design D4, D5, D6, D9)

- [x] 4.1 `wrt-containers apply` per Pod (D4).

  Verify: the services/containers tests pass on both boards.
- [x] 4.2 dae's lock, entry, reload and hotplug handler (D5).

  Verify: the network/transparent-proxy tests pass on both boards.
- [x] 4.3 `wrt-snap prune` by days (D6), and einat's check (D9).

  Verify: the storage/data-disk tests and the network/nat health check pass on both boards.

## 5. The mount triggers (design D7)

- [x] 5.1 procd.sh's `procd_mountpoints_mounted` and the unmount triggers' arguments (patch 0035), ksmbd's init (packages 0001), the log service (patch 0008); their write-ups in `docs/patches.md`.

  Verify: the services/file-sharing tests and the persistent log test pass on both boards.
- [x] 5.2 The test that compiles the image's ucode files, and firewall4's stray template removed (patch 0041) with its write-up in `docs/patches.md` (D11).

  Verify: the firmware/base-system test passes on both boards; it fails on an image without the exporter's patch.

## 6. config-push (design D8)

- [x] 6.1 The modes, the upload's removal, Tailscale's key file, the per-service save and restore, and the checks (D8); `docs/ops.md` where it describes them.

  Verify: the ops/config-push tests pass on both boards.

## 7. Integration

- [x] 7.1 Run every suite on both boards.

  Verify: no failure; record the runs.
  Done 2026-10-26/27 on the VM, from the change's branch on main's sync: every suite passed on both boards (R4S: upgrade 16, boot 24, system 294, network 48, services 39, release 72 tests; R6S: 16, 24, 295, 48, 39, 72).
- [ ] 7.2 Get a green CI run for both boards.

  Verify: record the run in `docs/ci.md`.

## Workflow follow-up

- Sync the delta specs, archive the change, merge it to main and push Codeberg first, then GitHub.
