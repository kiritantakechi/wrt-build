# Design

## Context

See proposal.md for why. The current state, in podman 5.8.4 and its vendored go.podman.io/storage 1.62.0 (the same in upstream's main):
- The overlay driver's home, `<root>/overlay`, is a bind mount of itself: the driver's `Init` binds it unless it is a mount point already (`mount.MakePrivate`), and its `Cleanup` unmounts it when a command ends with no layer mounted (`store.Shutdown`). The next command, or the next use of the store in one that runs on, finds it unmounted and binds it again.
- The store's graph lock is held "throughout the duration of Shutdown(), and the duration of any mount (but not unmount) calls" (store.go), so that the bind and the unmount stay apart from the mounts under the home. `Init` and `Shutdown` hold it, and so do the store's mounts of layers.
- `Init` probes the overlay itself, metacopy and the native diff under the graph lock. Three probes run later, when a feature is first asked about, each at most once per run root, whose `overlay` directory records the answers:
  - idmapped lower layers, from `SupportsShifting`: the driver's `Status`, a layer's creation, and the store's `canUseShifting` for a layer or a container;
  - volatile mounts: the driver's `Status`, and `Get`;
  - data-only lower layers, for composefs.
  Each makes a directory under the home (`compatNNN`, `volatile-checkNNN`), mounts in it, unmounts by path and removes it. `store.Status` and the creations hold the layer store's lock, not the graph lock.
- When another process binds the home while a probe has its mounts under the home's previous mount, the bind hides them. The probe's unmounts fail (`invalid argument`, a warning), the directory stays, and so do the mounts, under the previous mount, until a reboot. An unmount of the home while the probe runs detaches the probe's mounts along with it, so only a bind leaves them.
- The reproduction: the concurrency test on the R4S with the probes' records removed as they appear. Two of ten rounds left `compatNNN/lower-mapped` and `volatile-checkNNN/merged` mounted, with podman's warnings, and every command succeeded.

## Goals / Non-Goals

**Goals:**
- No probe of the storage leaves a mount behind, whatever the other podman commands do meanwhile, in a form that go.podman.io/storage could take.
- A concurrency test that shows a leaked mount where it happens, and finds it nearly every time without the fix.

**Non-Goals:**
- The store's undocumented use of the driver without the graph lock (its own FIXME), beyond what the probes need.
- Removing mounts that an earlier boot left: a reboot removes them.

## Decisions

### D1. A lock of the driver for its home's mount

The overlay driver gets a lock, `home.lock` in its run home (`<runroot>/overlay`), held:
- in `Init`, around `mount.MakePrivate(home)`;
- in `Cleanup`, around the unmount of the home;
- around each of the three later probes, with the cached answer read inside.

A bind and an unmount of the home then wait for a probe that has mounts under it, and the other way round. The lock is innermost: nothing takes another lock while holding it, so it adds no lock order. It lives in the run home, beside the probes' records and the layers' mount counts, the run time state of the same storage, and the runroot's tmpfs drops it at a reboot, as the probes' records.

This keeps two operations on one mount apart, as the graph lock already does for `Init`'s probes. It is not a serialization of work. A probe runs once per run root, so the waits are a bind's or an unmount's length, once per boot.

Alternatives considered:
- **The graph lock in `store.Status`**: the documented rule, and enough for `podman info`. But the creations' probes run under the layer store's lock, after which the graph lock cannot be taken (lock order), and holding the graph lock for a whole creation would serialize layer writes across processes.
- **The three probes in `Init`, under the graph lock**: upstream made them lazy so that a command that never asks about a feature does not probe it (volatile, c/storage 8e948dd, 2021); in `Init`, the first command after a boot would probe all three.
- **A probe that keeps a file descriptor of its directory and works through `/proc/self/fd`**: its unmounts would find its own mounts under any bind, but an unmount of the home while it runs detaches its directory's mount, and its next mount then fails: a wrong answer, recorded for the boot.
- **The probes' mount points outside the home** (in the run home): no bind covers them, but they would no longer be under the private mount that `MakePrivate` makes for this, and their mounts would propagate to peers of a shared `/run`.

### D2. The patch

`patches/packages/0007-podman-lock-the-storage-s-home-mount-for-its-lazy-fe.patch` adds `utils/podman/patches/021-overlay-lock-home-s-mount-for-the-lazy-feature-probes.patch` to openwrt/packages and sets podman's `PKG_RELEASE` to 5. The inner patch applies to `vendor/go.podman.io/storage/drivers/overlay/overlay.go`, its message written for go.podman.io/storage; the outer one carries `Upstream-Status: Pending`, and `docs/patches.md` has its write-up. It builds and vets for linux/arm64 with the host Go, and podman builds with it.

### D3. The concurrency test

`test_runtime_commands_at_the_same_time` keeps its rounds (eight commands at once on a fresh scratch storage, the run root behind a changing symlink) and:
- reports, per round, podman's errors and the mounts under the scratch storage once the commands have ended (`/proc/self/mountinfo`), and fails naming the number of rounds that left any and the first one's report;
- cleans up with the same step before each round and at the end: lazy unmounts of what is left under the scratch storage, then removal. The final cleanup does not raise, so it cannot mask the rounds' result;
- removes the probes' records (`idmapped-lower-dir-*`, `volatile-*` in the run root's `overlay`) as they appear, in a loop beside the symlink's, so every command probes, as the first commands after a boot do;
- runs three commands in a row in each of the eight, so binds, unmounts and probes keep overlapping through a round instead of only at its start.

### D4. Verification

- The test on the R4S without the patch, then with it, several runs each.
- The services system tests on both boards, then CI.

## Risks / Trade-offs

- [A probe waits for another process's bind or unmount] → Those take a mount call, once per command, and the probes run once per boot.
- [A process dies holding the lock] → fcntl locks end with their process.
- [Upstream prefers another form] → The patch is Pending; the write-up names the alternatives, and the test shows the leak either way.
