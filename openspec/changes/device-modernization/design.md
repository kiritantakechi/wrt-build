# Design

## Context

See proposal.md for why. The current state:

**Shell with JSON tools.**

| Script | Lines | JSON |
|---|---|---|
| `wrt-healthcheck` (wrt-ab) | 112 | builds its result with jshn; reads `ifstatus lan` with jsonfilter |
| `wrt-slot` (wrt-ab) | 54 | reads the result with jsonfilter |
| `fetch` (wrt-sync) | 72 | reads the GitHub release with jsonfilter; downloads with `uclient-fetch` |
| `config-push.d/device.sh` | 181 | reads `network.interface.lan status` with jsonfilter |

- `wrt-slot`, `wrt-healthcheck` and the sysupgrade hook (`lib/upgrade/wrt-ab.sh`) share `/lib/functions/wrt-ab.sh`: the running slot (from `/proc/cmdline`), the other slot, the partitions, and `fw_printenv`/`fw_setenv`.
- sysupgrade runs its hook from a ramfs in its second stage, as shell.
- wrt-metrics' rpcd plugin and the manifest helper are already ucode.
- jsonfilter itself stays in the image, as base-files depends on it (`/lib/functions/network.sh`).

**ucode in the image.**
- The image has ucode with its `fs`, `ubus`, `uci` and `digest` modules.
- `ucode-mod-uclient` exists in the pinned tree (`package/libs/uclient`).
- ucode runs a script from standard input (`ucode - <args>`).
- Pitfalls met before:
  - file I/O lives only in the `fs` module;
  - no destructuring;
  - `die()` exits 254;
  - a missing `-F` file is not an error.

**qosify on the WAN port.**
- qosify adds its classifiers with netlink (`cls_bpf` under `clsact`).
- It redirects DNS replies to `ifb-dns` with four u32 mirred filters, where a packet socket reads them.
- For ingress shaping, it redirects all ingress traffic to `ifb-<iface>` with a fifth filter.
- The order with einat holds because the kernel runs tcx before tc.
- A qosify killed with `SIGKILL` (procd does this when `SIGTERM` is not enough in time) leaves its filters attached.
- einat 0.1.11 attaches its programs with `TcxOrder(LinkOrder::first())`.
- The pinned libbpf (1.7.0) has `bpf_program__attach_tcx`.
- Patch 0010 makes qosify set an interface up anew on a device replaced under the same name.

**Key directory.**
- `/etc/opkg/keys` is read by sysupgrade's `fwtool.sh` (`ucert -P`) and by wrt-sync (`usign -P`), and written by wrt-keyring.
- The release scripts and the tests mirror the same layout.
- No release has been published.

## Goals / Non-Goals

**Goals:**
- No jshn or jsonfilter in this project's device code, and ucode wherever it handles structured data.
- One mechanism on the WAN port, tcx, with the order requested by the components themselves.
- No opkg name left in the image.

**Non-Goals:**
- Rewriting init scripts, uci-defaults or the sysupgrade hook in ucode: procd and sysupgrade call shell, and these scripts mostly start processes.
- Upstream's own scripts that use jsonfilter (`network.sh` and others).
- Moving qosify to a new upstream version, or submitting the qosify patch. Upstream would want a fallback to `clsact` for kernels without tcx, and submitting anything needs the maintainer's consent.
- Migrating keys on routers: none run a release yet.

## Decisions

### D1. The A/B tools in ucode, on a shared module

```
/usr/share/ucode/wrt/ab.uc       slot(), other(slot), getenv(name, default), setenv({name: value, ...})
/usr/sbin/wrt-healthcheck        ucode: ubus (system board, network.interface.lan), uci (limits),
                                 /proc/net/tcp{,6}, the checks in /etc/healthcheck.d, the JSON result
/usr/sbin/wrt-slot               ucode: the module and the result file
/lib/functions/wrt-ab.sh         POSIX sh, kept for the sysupgrade hook alone
```

**The module.**
- `setenv` writes every variable in one `fw_setenv -s -` and syncs, as the shell function does: a reset must not lose the write.
- `getenv` reads with `fw_printenv -n`.
- Both run the tools through `fs.popen`, and check their status.

**The checks** keep their semantics and time limits. A registered check still runs under `timeout` with the per-check limit, as an external program.

**Why two implementations of the slot facts.** sysupgrade's second stage runs from a ramfs that holds only the binaries sysupgrade copies there. Giving it ucode would mean copying the interpreter and its modules into that ramfs (`RAMFS_COPY_BIN`) for one function. The facts are small: which slot runs, which is the other, and how to write the variables. The A/B tests cover both implementations: the health-check tests the ucode one, the upgrade tests the shell one.

**Alternatives considered:**
- Keeping shell with a smaller JSON need, for example writing the result as `key=value`, would remove jshn but not the pattern. It would also make the result file a format of its own instead of the JSON the status command reads.

### D2. wrt-sync's fetch in ucode, with uclient

- `fetch` becomes a ucode script that uses `ucode-mod-uclient` for its requests, with the same retries, and parses the release natively.
- It still runs in wrt-sync's container, whose root is the host's, read-only.
- It still trusts nothing it fetches: the host checks the manifest with the existing ucode helper.
- wrt-sync's dependencies swap `jsonfilter` and `uclient-fetch` for `ucode-mod-uclient`.

### D3. config-push's device side in ucode, still sent per push

- `scripts/config-push.d/device.uc` replaces `device.sh`. config-push runs it as `ssh … ucode - <command> [args] < device.uc`, so the router never runs a stale copy.
- It reads `network.interface.lan` through the ubus module.
- It runs uci batches on a copy of `/etc/config`, `dae validate` and the services' reloads as external programs, and checks their exit status.
- Its commands, messages and rollback are those of `device.sh`, and `tests/ops/test_config_push.py` holds it to them.

### D4. qosify on tcx

```
WAN ingress (tcx):  einat ingress_rev_snat  ->  qosify_ingress_*   [-> bpf_redirect(ifb) when ingress shaping]
WAN egress  (tcx):  einat egress_snat       ->  qosify_egress_*    -> root qdisc cake
DNS learning:       AF_PACKET (SOCK_DGRAM) on each managed WAN device, filtered to source port 53
```

**Attach.**
- qosify attaches each classifier with `bpf_program__attach_tcx` and `BPF_F_AFTER` with no anchor, so it runs after every program attached so far.
- einat asks to run first. The order thus holds whichever starts first, and after any restart.
- The kernel keeps it, and the test "After restarting components" checks it.

**Lifetime.**
- The links belong to the daemon's process.
- A stop, a crash or a `SIGKILL` detaches them, and nothing stale stays on the port.
- A replaced device loses its link with the device, and patch 0010's device tracking attaches anew.

**DNS learning.**
- A packet socket bound to each WAN device that qosify manages, with a classic BPF socket filter that accepts UDP and TCP from port 53 over IPv4 and IPv6.
- It sees a copy of each reply, which itself goes on untouched.
- The DNS parser takes network-layer packets (`SOCK_DGRAM`) instead of Ethernet frames.
- This replaces `ifb-dns` and its four u32 filters.

**Ingress shaping.**
- When an interface has ingress shaping, its ingress classifier ends with `bpf_redirect()` to the interface's ifb. The ifb's index sits in a map entry per interface, which the daemon writes when it creates the ifb.
- The ifb returns the packets to the stack after cake, as with the mirred filter.
- Without ingress shaping, the map has no entry and nothing is redirected.

**Egress shaping.** Unchanged: cake as the root qdisc. A qdisc is not a filter.

**The patch.**
- One patch to qosify (interface, loader, DNS and BPF sources), carried by the patch series beside 0006 and 0010.
- It is registered in `docs/patches.md` as meant for upstream once it has a `clsact` fallback.

**Alternatives considered:**
- `bpf_clone_redirect()` of DNS replies to `ifb-dns` would keep the device, and rely on how an ifb treats clones it did not get from mirred. The packet socket needs neither.
- Keeping ingress shaping on a mirred filter would leave a legacy filter on the port whenever it is configured.

### D5. `/etc/usign/keys`

- The directory is named after the tool whose keys it holds, as `/etc/apk/keys` is. usign reads them, and so does ucert, which builds on them.
- `/etc/sysupgrade/keys` was considered and rejected: wrt-sync checks release manifests with the same keys.
- base-files' `fwtool.sh` reads `/etc/usign/keys`, or `/etc/opkg/keys` when the new directory does not exist, so the patch stays harmless for upstream's images.
- wrt-keyring, wrt-sync, `wrt-release.sh`, `release-keys.sh`, `release-sign.sh` and the tests' keyring (`wrt_tests.keys`) move together.

### D6. The code-standards check

- `scripts/check.sh` extends its forbidden-pattern check over the device code: the feed packages' `files/`, `files/` and `scripts/config-push.d/`.
- It fails on `jsonfilter`, on sourcing `jshn.sh`, and on `/etc/opkg`, naming the file and the line.
- Patches are upstream's code and are not checked.
- The check's test drives it on a copy of the repository with one offending line.

## Risks / Trade-offs

- [ucode code paths fail silently where the shell ones failed loudly, for example a missing module or a misread file] → Every script runs `'use strict'`, and checks the result of each call that can fail. Each snippet is first tried with the host ucode. The existing tests hold the behavior: health check, slot status, device sync and config push.
- [qosify's DNS learning sees replies before einat's reverse translation] → DNS learning reads only the DNS payload, which address translation does not change. The new "Classify by DNS name" test checks it.
- [qosify on tcx diverges from upstream qosify] → One registered patch. Its upstream form would add a `clsact` fallback, noted in the register.
- [The ingress shaping path is new code that the image's configuration never uses] → The "Enable ingress shaping" test exercises it in the emulator.
- [Two implementations of the slot facts drift apart] → They are small, and the A/B suites test both. A comment in each names the other.

## Migration Plan

- Firmware only.
- The key directory moves before the first stable release, so no router holds keys in `/etc/opkg/keys`.
- For a development router flashed with an earlier candidate, the next upgrade brings the new directory with the new image. The old one stays only in an overlay that copied it, and nothing reads it there.
- Rollback means reverting the change.
