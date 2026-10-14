# Tasks

## 1. The probes and the test (design D1, D2, D3)

- [ ] 1.1 Add the podman patch that gives the overlay driver its home lock (D1), as `patches/packages/0007-podman-lock-the-storage-s-home-mount-for-its-lazy-fe.patch` with `PKG_RELEASE` 5, and its write-up in `docs/patches.md` (D2).

  Verify: the driver builds and vets for linux/arm64 with the host Go, and podman builds with it; `just check` passes; both boards build.
- [ ] 1.2 Make the concurrency test report what each round leaves mounted and podman's errors, clean up without masking its result, remove the probes' records as they appear, and run three commands in a row in each of the eight (D3).

  Verify: without the patch, the test fails on the R4S, naming the probes' mounts; with it, the test passes on the R4S in every run.

## 2. Integration (design D4)

- [ ] 2.1 Run the services system tests on both boards (dev profile).

  Verify: all tests pass on both boards.
- [ ] 2.2 Get a green CI run for both boards.

  Verify: record the run in `docs/ci.md`, with the cause of run 38556156281's failures.

## Workflow follow-up

- Sync the delta spec, archive the change, merge it to main and push Codeberg first, then GitHub.
