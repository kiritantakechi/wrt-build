# Proposal

## Why

Three faults of the device side, each found in passing by an earlier change, break a spec or a component's own contract under conditions the tests did not reach:
- **SMB shares outlive the data disk.** ksmbd's init script (packages patch 0001) leaves out a share whose disk is not mounted and starts again when the disk is mounted, but nothing happens when the disk goes away. ksmbd keeps listing the share, against services/file-sharing's "When the data disk is absent, the SMB service MUST NOT offer any shares". Three layers are at fault:
  - procd's init-script helpers know mount triggers only for `mount.add`.
  - On a hot unplug, `block` makes blockd forget the device before it unmounts it, so blockd's `mount.remove` event names no mount point, or a stale one, and no trigger on `/mnt/data` could fire.
  - ksmbd's script returns early when nothing is left to share, before it unloads the server, so port 445 stays open.
- **podman refuses its own storage now and then.** CI run 37324813891 failed a device sync with `database run root "/run/containers/storage" does not match our run root "/tmp/run/containers/storage"`. podman resolves the symlinks of the recorded run root and of its own, which is the same string, in two calls, and each call resolves a path only if it exists. When a second podman process creates the run root between the two calls, the same path compares unequal. That happens with two podman commands at the start of a fresh `/tmp/run`, as wrt-containers and wrt-sync run them after a boot or a disk mount.
- **A service that outlives the data disk writes to the boot disk.** `block` removes the mount point after it unmounts the disk, so a path on the disk that a running process uses again, as a podman command's graph root, is created anew on the flash. Found by this change's own file-sharing test, it breaks storage/data-disk's "MUST NOT write data to the boot disk while a mount point is absent" for every service on the disk.
- **qosify names a long device's ifb from outside the name.** For a device name of 12 to 15 characters, `interface_ifb_name()` takes the name's tail from a negative offset: undefined behavior, and an ifb named after whatever precedes the name in memory. `qosify-status` derives the ifb's name in a way of its own, which disagrees with the daemon's for those lengths.

## What Changes

- **Mount triggers for both directions** (an openwrt patch to procd's `procd.sh`):
  - Init scripts can restart or act on `mount.remove` as they do on `mount.add`.
  - The helper names the calling script itself rather than relying on the caller's `$name`.
  - Several mount points become one condition that any of them satisfies.
  - The existing `mount.add` helpers keep their meaning for every package that uses them.
- **blockd names the unmounted mount point** (an openwrt patch to fstools): `block` unmounts a removed device before blockd forgets it, and blockd never reports another device's old mount point.
- **ksmbd withdraws its shares when their disk goes** (packages patch 0001, revised): the service restarts on the unmount of a share's mount point, and a start with nothing to share stops the server, port 445 included.
- **The data disk's mount point is read-only while no disk is mounted on it** (wrt-data): it lies on an empty read-only filesystem, mounted early in boot, so that nothing can write in the disk's place.
- **podman accepts its own storage at any concurrency** (a packages patch to podman): a recorded path equal to podman's own matches without resolving either, and resolution is left to paths that differ as strings.
- **qosify's ifb names fit the device name** (an openwrt patch adding a qosify patch):
  - A long name keeps its first two characters and its last nine.
  - `ubus call qosify status` reports each interface's ifb, which `qosify-status` reads instead of deriving it.
- Each patch is meant for its upstream (`Upstream-Status: Pending`), with its write-up in `docs/patches.md`, and is never submitted without the maintainer's consent.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `services/file-sharing`: the SMB service stops offering shares when the data disk is unmounted while it runs, not only when the system boots without it.
- `storage/data-disk`: the data disk's mount point is read-only while no disk is mounted on it.
- `services/containers`: container runtime commands that start at the same time all accept the storage recorded on `@containers`.
- `network/qos`: an interface's ifb has a name within the kernel's limit, derived from the device's name, and qosify's status reports it.

## Impact

- `patches/openwrt/`: new patches for procd (`procd.sh`), fstools (`block.c`, `blockd.c`) and qosify (`interface.c`, `qosify-status`).
- `patches/packages/`: patch 0001 (ksmbd-tools) revised; a new patch for podman (`libpod`).
- `feed/utils/wrt-data`: a preinit hook for the read-only mount point.
- `tests/services/test_file_sharing.py`, `tests/services/test_containers.py`, `tests/network/test_qos.py`, `tests/storage/test_data_disk.py`: a scenario each.
- `docs/patches.md`: the write-ups, including 0001's.
- Hot-unplugging the data disk stays unsupported for the services that keep files open on it (`docs/services.md`). This change makes the SMB service stop offering a disk that has gone, whatever the reason; it does not make the disk safe to pull.
- The patches change `procd`, `fstools`, `podman`, `qosify` and `ksmbd-tools`; the toolchain and its CI cache key are untouched.
- Order: device-robustness goes before build-integrity, so that the full rebuild that build-integrity brings comes once, at the end.
