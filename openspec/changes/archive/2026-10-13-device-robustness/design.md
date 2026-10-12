# Design

## Context

See proposal.md for why. The current state:

**How a mount reaches an init script.**
- The data disk is a plain fstab mount (`fstab.wrtdata`, target `/mnt/data`, no autofs). `wrt-data` enables it and announces the device with a `uevent` add; `/etc/hotplug.d/block/10-mount` runs `block hotplug`.
- blockd sends `mount.add` and `mount.remove` on its ubus object, with `{device, target}`. procd watches that object (`blockd.init` sets `watch block`) and matches the event names against its triggers exactly.
- `block` sends blockd `umount` before its lazy `umount2()`. blockd replies once `hotplug-call mount remove` has run, and it sends `mount.remove` when it is asked. So the event comes before the unmount: by the time of the reply in this image, which has no `/etc/hotplug.d/mount` script.
- On a hot unplug, `mount_action("remove")` first sends blockd `hotplug` with `remove`. blockd frees the device. Only then does `block` unmount, and blockd's `umount` handler no longer finds the device. Its `static char oldtarget[]` then keeps whatever an earlier unmount left, or nothing, and `mount.remove` names that.
- `procd.sh` has `_procd_add_action_mount_trigger <action> <path>...`. It finds the fstab mount points holding the paths (`procd_get_mountpoints`), and registers a `mount.add` trigger that runs the init script's action 1 s later (`PROCD_RELOAD_DELAY`). It passes the mount points as one quoted word, so several of them become one condition with a newline inside. The lower `_procd_add_mount_trigger` takes the event, but names the script from the caller's `$name`.
- Users of the mount helpers: ubox's log, ksmbd-tools, transmission, nfs-kernel-server (v3, v4) and postgresql. All use `mount.add` only.

**ksmbd's init script** (packages patch 0001):
- It leaves out a share whose mount point is not mounted (`/proc/mounts`), and registers a restart mount trigger for each share's path.
- With nothing left to share, it returns from `start_service` before `stop_service`, which unloads `ksmbd.ko`. So `reload` (which is `start`) leaves the server listening. `restart` is stop then start, and leaves nothing.
- mountd lists a share whatever its path, and the kernel keeps serving established tree connects from the detached filesystem.

**podman 5.8.4.**
- `ValidateDBConfig` (`libpod/sqlite_state.go`; BoltDB alike in `boltdb_state_internal.go`) compares the paths the database recorded at its creation with the runtime's own. For paths it calls `evalSymlinksIfExists()` on each side in turn. That resolves a path only if it exists at that instant, and cleans it otherwise.
- Unless `--runroot` is given, the runtime's own run root is the database's (`mergeDBConfig`), so both sides are the same string.
- The run root is created after the validation, in `GetStore()`. The image's run root, `/run/containers/storage`, goes through `/run` → `/var/run` → `/tmp/run`. A database created before the run root existed recorded it unresolved.
- So two processes starting together on a fresh `/tmp/run` can see the run root created between their two calls: the recorded side stays `/run/...`, and the own side becomes `/tmp/run/...`.

**qosify.** `interface_ifb_name()` builds `ifb-<name>` when it fits in `IFNAMSIZ`. Otherwise it takes the name's first two characters and then a tail at `name + len - (IFNAMSIZ + 6) - 1`, which is before the name for every length that gets there (12 to 15). `qosify-status` derives `printf %.16s "ifb-$ifname"`.

## Goals / Non-Goals

**Goals:**
- Each fix lies in the component at fault, in a form its upstream can take.
- The mount helpers stay what they are for their present users; unmount triggers are opt-in.

**Non-Goals:**
- Making a hot unplug of the data disk safe for services that keep files open on it (containers, logs). `docs/services.md` keeps telling to remove the disk only with the router off.
- Changing podman's or the podman package's paths. The race is podman's, and is fixed there.

## Decisions

### D1. Unmount triggers in procd.sh, symmetric with the mount ones

One internal helper registers a trigger for an event and an action:
- `_procd_add_mount_event_trigger <event> <action> <path>...` finds the mount points, names the init script itself (as `_procd_add_action_mount_trigger` does today), and passes the mount points as separate words: one per line of `procd_get_mountpoints`, so a mount point with a space stays whole.
- `_procd_add_action_mount_trigger` is it with `mount.add`, and the new `_procd_add_action_unmount_trigger` is it with `mount.remove`.
- The new wrappers `procd_add_restart_unmount_trigger` and `procd_add_reload_unmount_trigger` mirror the mount ones, and are exported with them.

`_procd_add_mount_trigger` keeps its signature and names the script from `$initscript` too. A direct caller then no longer depends on an unrelated `$name` of its own.

Alternatives considered:
- **One `mount.*` trigger for both directions:** procd matches `mount.*` by prefix, but blockd's `mount.ready` and autofs's events would restart the service too, and every present user would change behavior.
- **A raw trigger in ksmbd's script:** it would fix one package and leave the next one to find the gap.

### D2. blockd learns of an unmount before it forgets the device

- `mount_action("remove")` unmounts first and tells blockd that the hotplug device is gone after. blockd's `umount` handler then finds the device and its mount point, and `mount.remove` names `/mnt/data`.
- blockd's `umount` handler keeps the mount point in a local variable, empty for a device it does not know, instead of a static one that outlives the call. It sends the event with the target it knows, or none.

This is fstools' own ordering fault. Every `mount.remove` consumer, procd's triggers and hotplug's `mount` scripts alike, gets the mount point of a removed disk.

### D3. ksmbd reloads on the mount and the unmount of a share's mount point

- `service_triggers` registers, for each share, a reload trigger on the mount and one on the unmount (D1).
- A reload is a start for this script, which defines no `reload_service`, and `start_service` resets a running server hard first. So a reload does what a restart would, but procd updates the service in place.
- A restart is `stop` then `start`, and `stop` deletes the service from procd, its triggers included, until `start` registers it again. The file-sharing test lost the `mount.add` of a disk re-added two seconds after the unmount's restart: it arrived while ksmbd had no triggers. A reload keeps them throughout. An event during a running reload makes procd run it again after.
- With every mount point unmounted, the start that the reload is finds nothing to share, after the hard reset, and starts nothing. blockd sends `mount.remove` before `block` unmounts, so this counts on the trigger's 1 s delay. That is far longer than the time this image takes from the event to the unmount.
- `start_service` stops a running server before it returns with nothing to share: the hard reset now comes before that return.
- The changes amend patch 0001, which owns the script's mount handling. Its subject still holds; its message, `PKG_RELEASE` and write-up follow.

### D4. podman: identical recorded and own paths match without resolving

In `ValidateDBConfig`'s field check (SQLite and BoltDB), two equal strings are a match, and the symlink resolution is reserved for strings that differ. The race needs equal strings, which every runtime without `--runroot`/`--root` compares. Resolving the same string twice can only differ by the timing of a creation in between.

The patch goes to the packages feed's podman (`utils/podman/patches/`), through a new packages patch. Its message points at the class of fault podman fixed for the volume path (containers/podman#23515), as context for the maintainer.

Alternatives considered:
- **Canonical paths in the image** (`runroot = "/tmp/run/containers/storage"`, `tmp_dir = "/tmp/run/libpod"`): this avoids the symlinks, but leaves podman's race for any other path that goes through one. Databases created on existing disks also keep the unresolved path they recorded, as `mergeDBConfig` prefers it.
- **Creating the run root before validating:** this is closer to #23515, but it needs a storage-layer change, while the comparison is libpod's own.

### D5. qosify's ifb name: the intended tail, reported by the daemon

- `interface_ifb_name()` takes the tail at `name + len - (IFNAMSIZ - 7)`: the last nine characters after `ifb-` and the first two, fifteen in all, as the code evidently meant.
- `ubus call qosify status` adds `ifb` to each active interface that shapes its ingress.
- `qosify-status` shows that device instead of deriving a name of its own.
- The fix is a qosify patch (`104-...`) carried by a new openwrt patch, after 0034's 102 and 103.

Two long names that share their first two and last nine characters would still share an ifb. That stays as in upstream's scheme; a unique scheme would change every long name for a case no configuration here has.

### D7. The data disk's mount point lies in RAM

The file-sharing test found `containers` on the flash under `/mnt/data` once the disk was unmounted. `block` removes the mount point after a lazy unmount. A podman command that started before it, and touched its graph root after, created the path anew on the boot disk. Stopping each service on the unmount (D1) cannot cover a process that is already running. So the place it writes to must not be the flash:
- A preinit hook of wrt-data (`/lib/preinit/86_wrt_data_mountpoint`) mounts a small tmpfs (1 MiB) on the mount point's parent, `/mnt`. It runs after the overlay is mounted (`80_mount_root`), and before procd's coldplug lets `block` mount anything.
- Without the disk, whatever a process writes under the mount point lands in that tmpfs, in RAM. Once 1 MiB is used up, the write fails instead of growing. Nothing reaches the flash, and a reboot forgets it.
- The disk mounts on the mount point as before: `block` creates the directory when it is missing and removes it after an unmount, now in RAM.
- blockd's links to its automounts of unconfigured devices (`/mnt/<device>`) keep working in the tmpfs.
- `/proc/mounts` lists the tmpfs at `/mnt`, not at `/mnt/data`. So the checks that look for the disk's mount, ksmbd's `grep " /mnt/data "` and `wrt_data_mounted`'s btrfs line, are unaffected.
- sysupgrade's second stage mounts the new slot's boot partition at its own ramfs's `/mnt`, not this one.

What this costs: what lay under `/mnt` on the flash is hidden. The image puts nothing there.

Alternatives considered:
- **A read-only tmpfs over `/mnt`:** it made writes fail outright, but blockd could no longer create its `/mnt/<device>` links, and logged so at every boot for the boot partitions.
- **An immutable directory** (`chattr +i`): the image has no `chattr`, and the flag on an overlay directory depends on the lower filesystems.
- **A placeholder mounted at `/mnt/data` itself:** `/proc/mounts` would list `/mnt/data` without the disk, and every "is the disk mounted" check would have to tell the placeholder from the disk, upstream's ksmbd check included.

### D6. Tests

- **File sharing, "Data disk removed while sharing":**
  - With the shares offered, `echo remove` to the data disk's `uevent` goes the way a hot unplug goes: 10-mount, `block hotplug` remove, blockd and procd. The disk image stays attached.
  - Within a few seconds: `ksmbd.mountd` gone, `ksmbd.ko` unloaded, nothing on port 445, `smbclient --list` refused, and nothing under `/mnt/data` in the overlay's upper directory.
  - `echo add` mounts it again, and the shares come back.
- **Containers, "Runtime commands at the same time":**
  - In each of ten rounds, the test starts eight `podman --root ... --runroot ... info` at once, on a scratch storage whose run root does not exist yet. Every command must succeed. A scratch storage keeps the system's pods out of it.
  - Concurrency alone did not hit the two-resolution window in ten rounds on the unfixed podman, even with the run root behind 32 symlinks.
  - So the run root's path goes through a symlink that a background ucode loop keeps re-pointing, atomically, between two names of one directory (a bind mount). The path then resolves now to one name, now to the other, as a concurrent creation makes it resolve differently, while every file under it stays the same. All ten rounds failed on the unfixed podman.
- **QoS, "Ingress shaping on a device with a long name":**
  - A veth pair with 14-character names; a qosify `device` section with ingress shaping on one of them.
  - `ubus call qosify status` names the expected ifb, the ifb carries cake, and removing the section removes the ifb.

## Risks / Trade-offs

- [`mount.remove` precedes the unmount] → The reload runs 1 s after the event, while this image unmounts at once after it; a slow `/etc/hotplug.d/mount` script could delay the unmount by up to blockd's 3 s ubus timeout. The test exercises the real ordering.
- [A share's disk unmounted while clients hold files] → ksmbd's reload, a hard reset, drops their sessions. That is the point of the requirement: the disk is gone.
- [The concurrency test could pass by luck on a faulty podman] → Its symlink, re-pointed between two names of one directory, makes the path's resolution change all the time instead of once: all ten rounds failed on the unfixed podman, none passed by luck.
- [procd.sh is sourced by every init script] → The new helpers add functions only. The changed internals keep the existing helpers' triggers byte for byte for one mount point, as the existing users' triggers, compared before and after, show.

## Migration Plan

- The patches change installed scripts and binaries only. A router takes them with an upgrade, and databases recorded by older podman remain valid.
- Rollback is the previous release.
