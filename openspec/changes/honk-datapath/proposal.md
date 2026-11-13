# Proposal

## Why

dae's team now develops honk (github.com/daeuniverse/honk), a Rust engine that keeps dae's eBPF datapath design and its configuration syntax, and daeuniverse's own OpenWrt feed, LuCI pages and web UI (doona) target it. We move the transparent proxy to honk now, while it is a prerelease (v0.1.0-beta.6, 2026-11-08, "early alpha"), and carry what it lacks for this router as fixes in honk itself rather than as workarounds around it.

Two open honk bugs would break the router as it stands: with `lan_interface` set, a LAN client's IPv4 TCP connection to the router itself is rejected (honk #456: LuCI, SSH and SMB from the LAN), and on OpenWrt a configuration reload can end in a fatal NFQUEUE netlink error (honk #476). honk also has no offline configuration check, which config-push needs before it changes the device.

## What Changes

- **BREAKING**: dae, its uci configuration `dae`, `/etc/dae` and `luci-app-dae` are removed; honk takes their place as `honk`, `/etc/honk/config.dae` (dae syntax) and the LuCI page `luci-app-honk`. Nothing migrates: after the upgrade, config-push writes honk's configuration.
- **BREAKING**: the private config repository holds honk's configuration as `honk/*.dae.enc` instead of `dae/*.dae.enc`.
- honk is built from source: its userspace crates with the Rust of the build tree, raised to the version honk requires; its eBPF object for `bpfel-unknown-none` with the same rustc and a bpf-linker built from source against the same LLVM; doona, its web UI, from source with the Node that `flake.nix` pins, embedded through honk's `native-ui` feature.
- honk binds the LAN side only: br-lan, podman0 and tailscale0 are listed up front and bound when they appear, as honk binds interfaces lazily; no hotplug rebind is needed. honk attaches nothing to a WAN interface and no cgroup hook that steers the router's own traffic; on the cgroup2 root it attaches its `sock_ops` program, which acts only on sockets in its own namespace, and its socket-identity capture, which only records a socket's process.
- LAN DNS keeps dnsmasq: the firmware's part of honk's configuration sends DNS addressed to private addresses natively, so dnsmasq (and podman's aardvark-dns) answer it, and dnsmasq forwards external names to honk's DNS listener on 127.0.0.1:5353.
- Fixes in honk, as patches meant for upstream: LAN connections to the router's own addresses are delivered (#456); a reload does not end the process over NFQUEUE (#476); a `check` subcommand validates a configuration without applying it.
- The LuCI page comes from daeuniverse's OpenWrt feed (`luci-app-honk` on `luci-lib-daeuniverse`), pinned in `upstream.lock` as a fourth upstream with its own patch series; honk's package itself is ours, as dae's was.
- doona is reached through honk's native API, in static-token mode only: the token lives in the encrypted private configuration, the image's template keeps the API off, configuration writes through the API stay off, and the API answers only from the LAN zone.
- honk's packet marks and its nftables table `inet honk_nfqueue` are registered and checked like the other components'.
- A supply-chain review of honk (its git-pinned forks of boring-sys and quinn, its crates) and of doona, as `docs/supply-chain/honk.md`, replaces dae's.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `network/transparent-proxy`: honk instead of dae; its cgroup `sock_ops` program and socket-identity capture are allowed, nothing that steers the router's own traffic; the router's own services stay reachable from bound interfaces; configuration through the official LuCI page with its start-at-boot switch; doona through the native API in token mode; the health check.
- `network/dns`: honk's DNS listener; DNS to private addresses, the router's included, is answered natively.
- `network/tc-hook-order`: only honk's programs on the LAN-side interfaces and their bridge ports; honk's marks and nftables table registered.
- `ops/config-push`: honk's configuration, validated with honk's own check; honk's user configuration cannot set its interfaces.
- `release/device-sync`: the sync container's traffic is routed by honk.
- `services/containers`: container traffic is split by honk.
- `services/vpn`: Tailscale traffic is split by honk.
- `build/upstream-pinning`: daeuniverse's OpenWrt feed is pinned with the other upstreams.
- `release/upstream-bump`: the weekly bump checks daeuniverse's feed too.

## Impact

- Packages: `feed/net/dae` replaced by `feed/net/honk`; `feed/luci/luci-app-dae` removed; `upstream.lock`, `patches/daeuniverse/` (luci-app-honk, luci-lib-daeuniverse), patches to honk inside `feed/net/honk/patches`; OpenWrt's `lang/rust` raised if honk needs it (packages series); a host bpf-linker.
- Build environment: `flake.nix` gains Node and pnpm for doona; `config/datapath.seed`, `config/toolchain.seed`, kernel packages for NFQUEUE (`kmod-nft-queue`, `kmod-nfnetlink-queue`).
- Firmware files: `files/etc/uci-defaults/91-wrt-datapath` (dnsmasq, firewall rule for the native API), `files/lib/upgrade/keep.d/wrt-config`.
- Tools: `scripts/config-push.sh`, `scripts/config-push.d/device.uc`, `scripts/config-init.sh` and its skeleton, `scripts/image-audit.sh`; `feed/utils/wrt-sync`, `feed/utils/wrt-containers` (comments and behaviour that name dae).
- `config/marks.tsv`; docs (`docs/services.md`, `docs/ops.md`, `docs/release-flow.md`, `docs/patches.md`, `docs/supply-chain/`).
- Tests: `tests/network/test_transparent_proxy.py`, `test_dns.py`, `test_tc_hook_order.py`, `test_nat.py`, `tests/ops/test_config_push.py`, `tests/release/`, `tests/services/test_containers.py`, `test_vpn.py`, and `tests/wrt_tests/services/datapath.py`.
- The user's private config repository: `git mv dae honk`, and the configuration checked against honk's dialect (its differences from dae are listed in the design).
