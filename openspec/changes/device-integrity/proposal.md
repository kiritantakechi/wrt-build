# Proposal

## Why

An audit of the code that runs on the router (2026-10-26) found places where a failure goes unnoticed, input from outside is trusted too far, or a race decides the outcome. Each was checked against the code; several can cost a confirmed upgrade, a release's integrity, shares written to the flash, or a service left broken after a push:

- A trial boot whose confirmation could not be written is logged as confirmed; U-Boot rolls back three reboots later. An environment that cannot be read reads as "not on trial".
- An upgrade whose write failed still makes the half-written slot the trial slot; the configuration is copied only after that switch, so a power cut in between boots the new slot without it.
- The sync unpacks the release's `repo.tar` after verifying `manifest.json`, so a crafted archive replaces the verified manifest; any extra upgrade image lands in the release, and `wrt-update` takes the last one by name, which can be an older, validly signed release. The release tag from the API reaches paths and a shell command unchecked, and nothing flushes a release before it becomes current.
- One Pod that fails to start stops every Pod after it.
- dae's reload can be lost: its entry is rewritten without a lock, `dae reload` refuses while dae starts or reloads, and nothing retries; turning dae off in its configuration does not stop it.
- Snapshots are pruned by date: after a week without power, or with the clock set ahead, every older snapshot goes.
- `mount.remove` comes before the unmount, so ksmbd's reload still sees the disk mounted and offers the share again, onto the flash once the disk is gone. A share or log file under nested fstab mount points counts as mounted when any of them is.
- config-push leaves the secrets world-readable on the router, puts the Tailscale auth key on a command line, rolls back neither Tailscale's login nor the SMB users, and checks no service but dae, the network and Tailscale.
- einat's health check passes without checking anything when its interface is not set explicitly.
- Nothing checks that the image's ucode programs compile. The upstream pins of 2026-10-25 brought a ucode that rejects the node exporter's script, which only the monitoring tests' failures showed; firewall4 ships a template, committed by accident, that has never compiled.

## What Changes

- **The health check** tells an unreadable environment from one without a trial, and reports a confirmation it could not write; neither reboots.
- **An upgrade** checks every write, copies the configuration before it switches the slot, and switches only when all of it succeeded; the image's members are matched the same way the check and the write read them.
- **The sync** checks the tag, unpacks only the package repository's regular files, keeps only the upgrade image the manifest names, and flushes the release before it becomes current; **`wrt-update`** installs the image the manifest names.
- **`wrt-containers apply`** starts every Pod it can and fails at the end if any did not start.
- **dae's init script** writes its entry under a lock and atomically, a reload waits for dae to take it, and a reload of a disabled dae stops it.
- **Snapshots** are kept for the seven most recent days on which one was taken.
- **procd's unmount triggers** (patch 0035) tell the action which mount point goes away, and a new helper says whether every fstab mount point holding a path is mounted; ksmbd (packages 0001) and the log service (patch 0008) use them.
- **config-push** keeps the secrets readable by root alone, removes its upload however it ends, passes the Tailscale key in a file, saves and restores every file a service's push changes (Tailscale's state and the SMB users included), and checks every service it reloads.
- **einat's health check** uses the init script's default interface.
- **Every ucode file of the image** is compiled on the router by the image's own ucode, as ucode loads it; firewall4's stray template goes (patch 0041).

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `firmware/health-check`: an unreadable environment and an unwritten confirmation are failures that do not reboot.
- `firmware/ab-upgrade`: a failed write or configuration copy leaves the running slot the one that boots; the configuration is in place before the switch.
- `release/device-sync`: the upgrade image is the one the signed manifest names, nothing the sync downloads replaces the verified manifest, and a current release survives a power cut.
- `services/containers`: a Pod that fails to start does not keep the others from starting; a container stops and starts again, its network's DNS answering it, after a service's container ended.
- `services/file-sharing`: a share stops being offered as its disk is unmounted, whatever runs on the unmount; nested mount points all count.
- `network/transparent-proxy`: disabling dae stops it; an interface that appears while dae starts or reloads is still bound.
- `storage/data-disk`: snapshot retention by the most recent days that have snapshots.
- `ops/config-push`: secrets on the device are readable by root alone; the rollback restores and checks every service.
- `firmware/base-system`: every ucode file of the image compiles.

## Impact

- `feed/utils/wrt-ab`: `ab.uc`, `wrt-healthcheck`, `wrt-slot`, `lib/upgrade/wrt-ab.sh`.
- `feed/utils/wrt-sync`: `wrt-sync`, `wrt-update`, `libexec/wrt-sync/fetch`.
- `feed/utils/wrt-containers`, `feed/utils/wrt-data` (`wrt-snap`), `feed/net/dae` (init, hotplug), `feed/net/einat` (health check).
- `patches/openwrt/0035` (procd.sh), `patches/openwrt/0008` (ubox log), `patches/packages/0001` (ksmbd-tools), `patches/openwrt/0041` (firewall4).
- `scripts/config-push.sh`, `scripts/config-push.d/device.uc`.
- Tests in `tests/firmware`, `tests/release`, `tests/services`, `tests/network`, `tests/storage`, `tests/ops`; docs where they describe these.
