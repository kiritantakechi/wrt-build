# Design

## Context

See proposal.md for why. Each defect below was read against the code; the mechanisms that depend on other components were read in their source:
- fstools: `block` calls blockd's `umount` method before `umount2()`; blockd sends `mount.remove` at once, runs `hotplug-call mount` with `ACTION=remove`, and answers when the scripts end, so `mount.remove` announces an unmount still to come. `mount.add` follows the mount.
- dae 2.1.1: `dae reload` reads `/var/run/dae.pid`, which dae writes once it is ready, and refuses while another reload is in progress (`/var/run/dae.progress`); either refusal fails the command, and nothing asks again.
- OpenWrt's sysupgrade stage 2 (`do_stage2`) ignores `platform_do_upgrade`'s status: it copies the configuration with `platform_copy_config` and reboots whatever happened.
- `rc.common` passes a command's arguments on: `reload` without a `reload_service` runs `start_service "$@"`.
- `config_foreach` (`/lib/functions.sh`) splits the list of sections on `IFS`: run with `IFS` a newline, it takes the whole list for one section and finds none.
- procd 2026.10.18: a trigger's action runs after the trigger's delay (procd.sh's `PROCD_RELOAD_DELAY`, 1000 ms), and an instance restarts once the old one has stopped, within its `term_timeout` (twice that for a jailed one); `service list` reports each instance's `incarnation`, counted up whenever procd starts one, and with `verbose` each service's triggers and their delays. Nothing reports the actions still to come.
- procd 2026.10.18 (39b5aac8c1) kills what an instance leaves in its cgroup once the instance's main process exits. podman moves conmon and the containers into `libpod_parent`; netavark starts aardvark-dns, the DNS of podman's network, in the cgroup of whatever ran it, so the first service that ran a container and ended (wrt-sync, `wrt-containers apply`) took it along, its pid file staying. Stopping the network's last container then started aardvark-dns on an empty configuration, which exits at once, and failed. The sync's packages patch 0009 has netavark run aardvark-dns in a cgroup of its own.
- `tailscale up` takes an auth key only to log in anew: a node that is logged in keeps its login, unless `--force-reauth` is given.
- A shell's exit trap runs where `exit` was called: in a function such as `die`, `"$@"` is that function's arguments.
- BusyBox 1.38: `tar -tv` lists a symbolic link as type `l` and a hard link as a regular file (`-`), each followed by ` -> <target>`; `tar -t` lists the names alone. `ln -sf` removes the old link before it makes the new one; `mv -T` renames over a link.

## Goals / Non-Goals

**Goals:**
- Every defect of the proposal fixed where it lies, in a form the component's upstream could take where it is upstream's (procd.sh, ksmbd-tools, ubox).
- Each spec scenario of the change tested on both boards, and each test failing without its fix where the emulator can provoke the fault.

**Non-Goals:**
- Retrying a Pod that failed to start: the scenario asks that it not keep the others down; starting it later is the next mount's or the administrator's.
- Covering `repo.tar` with the signed manifest: it is assembled when the release is published, after signing. The router accepts only what the signed package indexes and the manifest cover (D3).
- A sysupgrade during an unconfirmed trial, and a confirmed slot whose root does not mount: design questions of the A/B scheme, not defects of this code.

## Decisions

### D1. The health check reads the environment once, and knows when it cannot

`wrt.ab` gets `variables()`: the U-Boot environment as an object of its variables, from one `fw_printenv`, or `null` when the tool fails. `getenv()` goes; `wrt-healthcheck` and `wrt-slot` read `variables()` once.
- An environment that cannot be read is the failed check `environment` in every round; the trial state is unknown, so the health check never reboots for it.
- A pass in the trial state records `pass` only once `setenv()` wrote the confirmation; otherwise it records `fail` with `confirm`, logs an error, and does not reboot: the slot stays on trial, and U-Boot decides at the next boots.
- `wrt-slot status` says the state is unknown when the environment cannot be read.

### D2. An upgrade switches only after everything it wrote

In `lib/upgrade/wrt-ab.sh`:
- The members are listed whole. The check accepts exactly `<dir>/CONTROL`, `<dir>/kernel` and `<dir>/root` of one directory, and the write extracts `<dir>/<name>`: the check and the write read the same names.
- Each write runs with `pipefail` in a subshell, so a failing `tar` fails it as a failing `dd` does; the overlay's clearing is checked too.
- The configuration goes into the new slot's boot partition inside `platform_do_upgrade`, before the environment changes, when `UPGRADE_BACKUP` is set (stage 2 exports it). `platform_copy_config` is a no-op that says so: it still has to replace the platform's whole-disk one.
- Any failure returns before `wrt_ab_setenv`; stage 2 reboots into the running slot.

### D3. The sync keeps what it verified, and nothing else

- `fetch` refuses a tag that is not `^[A-Za-z0-9][A-Za-z0-9._-]*$` (no `.` or `..`, no slash or quote) before it uses it; `wrt-sync` checks the container's answer the same way. The names `fetch` passes to the manifest helper are quoted.
- After `manifest.json` verifies, `wrt-sync` lists `repo.tar` and refuses it unless every member is a regular file or a directory under `packages/` or `targets/packages/`, with no `..` component and no link. The names come from `tar -t`, as a name may hold spaces; the types, line for line, from `tar -tv`, where a link of either kind shows its target. Then it builds the release in a directory of its own from the verified parts only: the manifest and its signature, the upgrade image the manifest names, and the package repository. The checks of D3's existing loop run there.
- What a sync downloads and builds goes when it ends, however it ends: `.incoming` and the release in the making are removed on exit, once the sync holds its lock. `fetch` downloads afresh every time, so a refused release's files serve no later sync.
- `sync` flushes the release before `mv` makes it a release. `current` then changes by one rename over the link, a new link made beside it and moved with `mv -T`, and `sync` flushes that before `wrt-sync` says the release is current: a power cut leaves one release current or the other, never none.
- `wrt-update` installs the image the current release's manifest names (`manifest image`), and prints it.

### D4. Every Pod gets its turn

`wrt-containers apply` runs each declaration's step in a subshell of its own; a step that fails is logged with its name and the loop goes on. The command fails at the end, naming the Pods that did not come up.

### D5. dae's entry: locked, replaced whole, and taken

- Every path that writes the entry or signals dae (start, reload, the hotplug handler) holds `/var/lock/dae.lock` (`flock`).
- `/var/run/dae` stays; its links follow the configuration's directory (stale ones go, missing ones come), and `main.dae` is written beside and renamed over, so a dae that starts or reloads meanwhile reads the old entry or the new, never part of one.
- `reload_service` stops dae when `enabled` is 0, starts it when it does not run, and otherwise writes, validates and has dae reload, asking again every 2 s for up to 50 s while `dae reload` refuses (not ready, or busy).
- The hotplug handler runs the reload in the background, so the hotplug queue does not wait for it.

### D6. Snapshots by their most recent days

`wrt-snap prune` keeps, for each subvolume, the snapshots whose day (UTC, from the name) is among its 7 most recent snapshot days, and deletes the rest. A clock set ahead, or a long time off, then costs at most one day's worth.

### D7. Unmount triggers name the mount point; mount points count all

In procd.sh (patch 0035):
- `procd_mountpoints_mounted <path>...` succeeds when every fstab mount point that holds any of the paths is in `/proc/mounts`. One awk reads `/proc/mounts` first, its mount points unescaped as the kernel escapes them, then the list `procd_get_mountpoints` writes to it, and fails at the first mount point it has not seen. The list is not split by a newline `IFS` in the shell: `procd_get_mountpoints` would run with that `IFS`, and its `config_foreach` find no mount point at all.
- An unmount trigger is one trigger per mount point, whose action runs as `<action> unmounting <mount point>`: `mount.remove` comes before the unmount, so the action learns which mount point goes, instead of finding it still mounted.

ksmbd's init (packages 0001) takes `unmounting <mount point>` in `start_service` and leaves out every share on that mount point, and the others unless `procd_mountpoints_mounted` holds. The log service (patch 0008) uses `procd_mountpoints_mounted` too.

### D8. config-push: root's files, a cleaned upload, and a full rollback

- `config-push.sh` runs under `umask 077`, so the archive's files are 0600 and its directories 0700; the router side creates `/tmp/wrt-push` under `umask 077` before anything else, and a trap removes it on any exit after the upload. Every command on the router goes through one function, `router`, which builds ssh's arguments itself: the trap runs inside `die` as well.
- Tailscale's login is two files, `auth_key` and `options`; the router keeps them as `/etc/wrt-config/tailscale.key` (0600) and `tailscale.options`, and logs in with `tailscale up --reset --force-reauth --auth-key=file:<key> <options>`: without `--force-reauth`, a node logged in already would ignore the pushed key, and a refused key would go unnoticed. A previous `tailscale.login` goes with the first such push.
- `device.uc` saves and restores, for each service, every path its write changes, an absent path included (restoring removes it): dae, `/etc/dae` and `/etc/config/dae`; pods, the Pods' directory; smb, `/etc/passwd`, `/etc/group` and `/etc/ksmbd/ksmbdpwd.db`; tailscale, its two files and tailscaled's state file (`tailscale.settings.state_file`); the uci services, `/etc/config`. A restored Tailscale restarts tailscaled on its old state instead of logging in again.
- The command that reloads a service must succeed: `tailscale up` fails on a key control refuses, while tailscaled keeps its earlier login and `tailscale status` reports it running. Putting a service back reloads it the same way, its command's failure counted alike.
- `back()` keeps the network's, dae's and Tailscale's own checks, and every service adds the general one: no procd instance that ran before the push and is respawned when it ends (a daemon) has stopped (`service list`, read before the write). smb also needs ksmbd running while its configuration offers a share; pods, every declared Pod running. A service is back once the checks, 2 s apart, pass with every such daemon in one incarnation for as long as procd may take to act on the change: its longest trigger delay, then twice the longest `term_timeout` among the daemons, then one more check for the init scripts it runs. A reload still to come (`reload_config` leaves it to the triggers), a restart under way and a daemon that fails and is respawned, which runs for a moment at a time, each break that run.
- A put-back file is replaced in one rename, and a put-back directory gets its copy over it, then loses what the push added: neither is missing meanwhile.
- Each service's hash takes its files' names NUL-separated in C order, and the push fails when a file cannot be hashed: a name with a blank, or a locale's collation, no longer changes or drops a file from the hash.

### D9. einat's check uses the init script's interface

The health check reads `einat.config.ifname` with the init script's default, `pppoe-wan`.

### D11. The image's ucode files compile
A firmware test compiles, on the router, every ucode file of the root filesystem with the image's ucode (`ucode -c`), as ucode loads it: a template (`*.ut`, fw4's templates, a file that starts with a template block or whose interpreter line asks for one) with `-T`, a module (an `export` at its top level) with `-c module`, any other `*.uc` file and every executable whose interpreter line names ucode as a script. Of the executables it reads the first line alone: `grep -r` over the root filesystem took 11 s natively, past the test's 300 s under emulation. It also requires one file of each kind among those it compiled, so that a check that finds no files fails.

firewall4's `mangle-rule.uc` came with commit 39e8c70957 by accident, beside `ruleset.uc.orig` and `ruleset.uc.rej`, which upstream removed since. Nothing includes it, and its first block lacks its `%}`: neither the ucode of the earlier pins nor the current one compiles it. Patch 0041 adds a firewall4 patch that removes it.

### D10. Tests

On both boards, in the suites that hold their capabilities:
- firmware/health-check: "Environment that cannot be read" and "Confirmation that cannot be written" run the health check with `PATH` led through a directory whose `fw_printenv` or `fw_setenv` fails.
- firmware/ab-upgrade: "Write that fails" runs `platform_do_upgrade` on an image cut short inside its root member; "Configuration in place before the switch" runs it with `UPGRADE_BACKUP` and a `wrt_ab_setenv` that records whether the target's boot partition holds the backup.
- release/device-sync: the Releases stand-in serves a package archive with a manifest, an image, a symbolic link and a hard link; a release named `..`; a power cut right after a sync; and `wrt-update -T` with an older signed image beside the release's.
- services/containers: two declarations, the first naming an image no registry has; wrt-sync restarted and ended, its container with it, then the app Pod stopped and started, its own name looked up inside it.
- services/file-sharing: a removal with a mount script that sleeps 5 s on `remove`; a share under nested fstab mount points of which only the outer is mounted (tmpfs).
- network/transparent-proxy: `enabled` set to 0 and applied as LuCI applies it, through rpcd's `uci apply`, which announces the change to procd (`reload_config` compares with the configuration it saw last, and the tests' dae was enabled by a commit of its own); podman0 created right after dae's restart.
- storage/data-disk: the daily job on 7 days, then once 10 days later.
- ops/config-push: modes and leftovers after a push (and a failed one), with a `tailscale` wrapper that records its arguments; a Tailscale login with a key Headscale refuses; a uci batch that stops a running service.
- firmware/base-system: the image's ucode files compiled on the router (D11).

## Risks / Trade-offs

- [`pipefail` missing from the shell] → BusyBox ash has it with `ASH_BASH_COMPAT`, which OpenWrt enables; the upgrade test fails if the option is missing.
- [A reload that waits holds the lock for up to 50 s] → Only while dae refuses; a hotplug reload waits in the background, and LuCI's hot reload waits as long as dae takes.
- [Arguments to an unmount trigger's action] → Scripts that take none ignore them; the helper's comment states the convention.
- [Tailscale's `file:` auth key] → Supported by every tailscale the feed has carried since 1.42.
