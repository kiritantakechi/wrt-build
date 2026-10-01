# Proposal

## Why

The device code still carries three idioms of OpenWrt's earlier days, and they are the legacy the board-model exploration agreed to remove:
- Shell scripts that parse JSON with jsonfilter and build it with jshn, a field at a time, through pipes whose failures are easy to lose. ucode has native JSON and ubus, uci and fs bindings.
- sysupgrade's trust anchors in `/etc/opkg/keys`, although opkg left the image long ago.
- qosify's classifiers and DNS redirects as legacy tc filters on the WAN port, while everything else there runs on tcx. The order of the two is held by the kernel's rule that tcx runs before tc, not by anything either component asks for. A daemon killed outright leaves its filters behind.

The rpcd plugin, also on that list, turned out to be a ucode plugin already.

## What Changes

- **ucode for the device tools that handle structured data**:
  - `wrt-healthcheck` and `wrt-slot` share a ucode module for the A/B facts: the running slot, the other slot and the U-Boot variables. They read ubus, uci and their result file natively.
  - wrt-sync's `fetch` helper uses ucode's uclient and JSON instead of `uclient-fetch` and jsonfilter.
  - config-push's device side becomes a ucode script, still sent over SSH for every push.
  - jshn and jsonfilter leave this project's code, and wrt-ab and wrt-sync depend on ucode modules instead.
  - What only orchestrates processes stays POSIX sh, because procd and sysupgrade call shell: init scripts, uci-defaults, and the sysupgrade hook with its A/B library.
- **qosify on tcx** (a qosify patch):
  - Its classifiers attach as tcx links after every other program. einat already attaches its own first, so the order on the WAN port holds whatever starts first, and the links go away with the daemon.
  - Its DNS learning reads DNS replies from a packet socket on the WAN device, filtered to source port 53. This replaces the `ifb-dns` device and its four u32 redirect filters.
  - Ingress shaping, when configured, redirects to the interface's ifb from the BPF program instead of a mirred filter.
  - No legacy tc filter is left on the WAN port.
- **Trust anchors in `/etc/usign/keys`**:
  - wrt-keyring installs the firmware keys there, and sysupgrade's `fwtool` reads them there: a base-files patch, which falls back to `/etc/opkg/keys` for upstream's images.
  - wrt-sync and the release scripts follow, and the image has no `/etc/opkg` at all.
  - No release has been published, so no router holds keys in the old place.
- **A code-standards check** keeps jshn, jsonfilter and `/etc/opkg` out of this project's device code.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `network/tc-hook-order`: only tcx programs on the WAN port, einat's first and qosify's after, with no legacy tc filter and no `ifb-dns`.
- `network/qos`:
  - no ifb device at all, as DNS learning no longer needs `ifb-dns`;
  - classification by DNS name gets its scenario: it was untested, and its capture changes;
  - ingress shaping, when configured, goes through the interface's ifb (new requirement).
- `firmware/base-system`: the image has no `/etc/opkg`.
- `quality/code-standards`: device code handles JSON, ubus and uci in ucode, never with jshn or jsonfilter (new requirement).

## Impact

- **Feed packages**:
  - `wrt-ab`: `wrt-healthcheck`, `wrt-slot`, a ucode module and its dependencies;
  - `wrt-sync`: `fetch`, the key directory and its dependencies;
  - `wrt-keyring`: the key directory.
- **Files and scripts**:
  - `files/lib/upgrade/wrt-release.sh`;
  - `scripts/config-push.sh`, with `scripts/config-push.d/device.uc` replacing `device.sh`;
  - `scripts/release-sign.sh` and `scripts/release-keys.sh`.
- **Patches**: one to base-files (`fwtool`'s key directory), and one to qosify (tcx, DNS capture, ingress redirect). It is carried by the patch series, builds on patch 0010's device tracking, and is registered in `docs/patches.md`.
- **Tests**:
  - `tests/network/test_tc_hook_order.py`;
  - `tests/network/test_qos.py`: DNS name, ingress shaping;
  - `tests/firmware/test_base_system.py`;
  - `tests/wrt_tests/keys.py`;
  - the code-standards check and its test.
- **Docs**: `docs/release-flow.md`, `docs/ops.md`, `docs/patches.md`.
- **Order**: after `toolchain-o3`, whose patch register this change adds to, and whose audit covers qosify's earlier patches.
