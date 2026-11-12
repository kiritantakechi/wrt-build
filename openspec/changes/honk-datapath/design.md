# Design

## Context

See proposal.md for why. What shapes the approach, read in honk v0.1.0-beta.6 (2026-11-08) and daeuniverse/openwrt-packages at 6157f709f52c (2026-11-11):

- **Build.** honk's workspace pins Rust 1.99.1 (`rust-toolchain.toml`); OpenWrt's `lang/rust` at our packages pin is 1.96.1, built from source with `rust-src` and `llvm-tools` in its dist. `crates/honk-ebpf` is outside the workspace, `#![no_std]`/`#![no_main]` with no feature gates, and builds with `-Zbuild-std=core --target bpfel-unknown-none` and bpf-linker (honk pins 0.11.0, which takes LLVM 21, 22 or 23). `crates/honk-core/build.rs` reuses a prebuilt object only when a sibling `.toolchain` file names honk's nightly exactly; otherwise it runs `cargo +<nightly>` itself, which needs rustup. Git dependencies: `Glassyiris/boring-sys` (rev 3beb573, REALITY hooks) and `Glassyiris/quinn` (rev 11f1de8, BBRv3 and flow-control changes); 466 packages in Cargo.lock. boring-sys builds BoringSSL (C/C++, cmake, bindgen), so honk needs libstdc++ on the router. The feature `native-ui` embeds doona from `HONK_DOONA_DIR`; doona is TypeScript, pnpm 11 and vite, Node ^22.13, ^24 or ≥26.
- **Datapath.** honk binds `lan_interface` lazily: a missing interface does not fail startup, and one that appears later, or is recreated, is bound (since beta.3). With `wan_interface` empty it attaches no WAN programs and none of its `sock_create`/`connect`/`sendmsg` cgroup programs, but its `honk_tcp_passive` `sock_ops` program on the cgroup2 root is required: it acts only on sockets in honk's own `daens`. It appends TCX links after existing ones. It writes sysctls regardless of `auto_config_kernel_parameter` (forwarding on, `rp_filter=0` on `dae0` and on the first LAN interface). With NFQUEUE (on by default) it installs table `inet honk_nfqueue` itself, over netlink, at prerouting priority -250, queue 320. Marks: 0x08000000 tproxy, 0x100 bypass, 0x40000000 classified, 0x80000000 NFQUEUE pending.
- **DNS.** honk sends LAN TCP/UDP to port 53 through its traffic routing even when a local socket listens on `:53`; only a `direct(must)` result leaves it native. `dip(geoip: private)` is a built-in CIDR set, without geodata.
- **Configuration.** honk merges every top-level section across the entry and its includes, entry first, then includes in declaration and glob order; an include must resolve, canonically, inside the entry's directory. Its dialect differs from dae's in ways that matter for the private configuration (D11).
- **Control.** SIGHUP or `honk-core reload` reloads; the outcome is only logged, and changes to restart-only fields are refused. There is no offline check: validation exists only as an authenticated native API endpoint. A successor waits up to 240 s for the old process's lock; shutdown can take over 10 s.
- **Official OpenWrt packaging.** `honk/Makefile` builds from a CI checkout with rustup and downloads crates during Compile; `luci-app-honk` on `luci-lib-daeuniverse` offers an editor of `/etc/honk/config.dae` and its includes, start/stop/restart, a start-at-boot switch (rc.d, no uci `enabled`), the log, an apk upgrade helper for its packages, a doona switch that writes a `native_api` block with password login and `config_write: true`, and a "store db" switch.
- **Bugs.** honk #456: with `lan_interface` set, IPv4 TCP from the LAN to the gateway's own addresses intermittently fails ("accepted TCP child is unproven", Debian 13, beta.5). honk #476: on OpenWrt 25.12 (x86-64, beta.5 and beta.6), a configuration reload ends in `NFQUEUE listener failed: unexpected netfilter netlink message type 2` and procd respawns honk.

## Goals / Non-Goals

**Goals:**
- Every requirement of the change met on both boards, with the full suites, honk built from source with the build tree's toolchains.
- The two honk bugs and the missing offline check fixed in honk, in forms honk's upstream could take, each with a test that fails without its fix.

**Non-Goals:**
- honk on the WAN interface, its host-traffic interception or `wan_interface: auto`: the router's own traffic stays direct.
- Geodata packages: the image ships none, as before; `geoip: private` needs none.
- A Clash-API dashboard: honk's Clash API is not built (D8).
- honk's database store (`--store db`) and configuration writes through its API: the files stay canonical.
- Submitting the patches upstream (they stay `Pending` until the user decides).

## Decisions

### D1. honk is our package; the LuCI pages come from daeuniverse's feed, pinned

`feed/net/honk` builds honk from its release tag's source archive, hash-verified like every other package, with this build's toolchains (D2, D3). Our feed already wins over a feed's package of the same name (`scripts/patch.sh`), so it replaces daeuniverse's `honk` for `luci-app-honk`'s `+honk` dependency.

daeuniverse/openwrt-packages joins `upstream.lock` as `daeuniverse`; `fetch.sh`, `patch.sh` and `upstream-bump.sh` already iterate over the lock. Our adaptations of its LuCI packages are a patch series, `patches/daeuniverse/`, so the weekly bump carries its fixes and the series shows what we change.

Alternatives: vendoring the LuCI packages into our feed, as luci-app-dae was (no weekly tracking of a project that changes daily); patching daeuniverse's `honk/Makefile` (its build depends on a CI checkout and rustup, so a patch would replace it whole).

### D2. One rustc for honk and its eBPF object; bpf-linker from source

honk's userspace crates build with OpenWrt's host Rust through `rust-package.mk`, as einat does. If honk does not build with 1.96.1, `lang/rust` is raised to the version honk pins, as a packages patch meant for upstream.

The eBPF object builds with the same rustc: `RUSTC_BOOTSTRAP=1` admits `-Zbuild-std=core` for `bpfel-unknown-none`, and `rust-src` comes with OpenWrt's Rust. honk-ebpf uses no unstable feature, so the bootstrap flag only unlocks build-std. bpf-linker becomes a host package built from its release source, with its Cargo.lock, against the LLVM of `flake.nix` whose major equals that rustc's LLVM. A rustc's bitcode must be read by an LLVM no older than its own; the BPF objects of other packages already compile with the flake's clang (`CONFIG_BPF_TOOLCHAIN_HOST`). The first task proves this toolchain on honk-ebpf before anything depends on it.

`build.rs` takes the object through a new environment variable instead of the nightly marker file, a patch meant for upstream: distribution packagers build the object in a separate step, as we do.

Alternatives: a nightly rustc from a Nix overlay (a second Rust toolchain and supply chain, against the one-toolchain rule of the build); honk's prebuilt release binaries or eBPF object (not built from source); bpf-linker 0.9.15 from nixpkgs (older than honk's pin, against nixpkgs' rustc LLVM).

### D3. doona from source, embedded

doona is a host package of our feed: its tag's source, hash-verified, built as its own release is: `pnpm install --frozen-lockfile` (its lockfile's integrity hashes verify every dependency), `pnpm build`, `pnpm -C apps/lite build`, then its `tools/package.sh`, which adds the licence notices of each edition. Both editions land in the host staging directory, where honk's `native-ui` feature embeds them through `HONK_DOONA_DIR` and its `-lite` sibling. doona's version is the one honk's `pins.env` names for the honk release.

`flake.nix` gains Node, as it provides Go, and brotli for the packaging. pnpm is the exact version doona's `packageManager` names, a hash-verified download of the doona package run by that Node: the pinned nixpkgs has pnpm 10 only.

Alternatives: doona's release tarballs, hash-pinned (not built from source); pnpm 10 from nixpkgs (another major than doona's lockfile was made with); leaving doona out (the user chose it).

### D4. The firmware's part of the configuration is an entry around the user's

The init script copies the configuration's directory to `/var/run/honk`, readable by root alone, and writes two files of its own there: the entry `wrt-entry.dae` and the firmware's settings `wrt-settings.dae` (a configuration that has either name is refused). honk resolves includes from the entry's directory and takes one only from inside it, so the configuration's own includes resolve as they do in its directory (copies, since links would resolve outside it). The entry holds:

```
routing { dip(geoip: private) && dport(53) -> direct(must) }
include { config.dae; wrt-settings.dae }
```

and the settings:

```
global { lan_interface: br-lan, podman0, tailscale0; wan_interface: ''; data_dir: <D5> }
dns { bind: '127.0.0.1:5353' }
```

honk merges the entry's sections first, then the included files in order, and takes a scalar setting from the last file that has it (`raw_fields`, shown by a probe of honk's parser: an entry, a user file and a last file each setting `lan_interface`, `wan_interface` and `data_dir` give the last file's values, and `wan_interface: ''` an empty list). So the firmware's routing rule precedes every user rule, and its settings, included last, win over the configuration's, whichever way it was written: config-push also rejects `lan_interface`, `wan_interface` and `data_dir` explicitly, a LuCI edit is overridden. (The first layout put the settings in the entry, on the premise that the entry's would win; they would have lost to the configuration's.) Listing podman0 and tailscale0 up front replaces dae's hotplug rebind, since honk binds them when they appear.

DNS to any private address stays native: dnsmasq keeps answering the LAN (local names, DHCP names, rebind protection, the fallback when honk stops), podman's aardvark-dns answers containers on podman0's gateway, and dnsmasq forwards external names to honk's listener. Public resolvers a client addresses directly are still intercepted by honk.

Alternatives: honk answering all LAN DNS, with `.lan` routed back to dnsmasq (loses dnsmasq's protection and logging for the LAN, and the fallback path changes); `dip()` of the router's own addresses (they change with the delegated prefix and podman's bridge, so the entry would need rewriting on address events).

### D5. Service control as the official LuCI page expects it

There is no uci `enabled` option: honk runs while its init script is enabled, as the start-at-boot switch sets it. The image ships the service disabled through a build option the image builder already has and a build from source lacks, `TARGET_DISABLED_SERVICES` (openwrt 0046, meant for upstream); an upgrade keeps honk's rc.d links (`keep.d`), so a new router starts without honk and an upgraded one as it was. daeuniverse's uci-defaults, which disables honk on every first boot of an image, would turn it off on every firmware upgrade. config-push writes the configuration, enables and restarts honk. procd runs honk with respawn and `term_timeout` 30 s (honk's graceful shutdown; its unit uses `TimeoutStopSec=30s`). The entry's directory is made anew beside the running one, checked with honk's check (D7) and only then put in its place, so a configuration honk refuses never reaches the running entry. `reload_service` does that, then signals honk (SIGHUP). A LuCI save reloads; config-push restarts, so changes to restart-only fields take effect. The uci configuration `honk` keeps `config_file` and `cpu_pinning`. The pinning is the cpuset of honk's service cgroup on the big cores rather than dae's `taskset` prefix: it moves a running honk at once, so a reload takes it, and the command line stays the same.

honk's data directory holds its state database (cached DNS answers and delay samples, written all the time, the cached subscriptions, the geodata schedule) and the geodata its update fetches (decided: the update stays on, as honk ships it). Its default, `/var/lib/honk`, is RAM on OpenWrt: every boot would start without geodata, and honk's first update waits five minutes and up to an hour of jitter, so rules on geosite or geoip codes would match nothing for that long. The boot disk takes no such writes (r4s-services D1), so the directory follows the data disk (user's choice): `/mnt/data/honk` while the data disk is mounted and writable, RAM otherwise. The data directory is fixed for a running honk, so the data disk's mount and unmount restart honk (procd's mount triggers, as for the other services on the disk); without the disk honk proxies as before, its state in RAM.

### D6. Health check: the process and its programs

`/etc/healthcheck.d/50-honk` passes while honk is disabled; otherwise when honk runs and `bpftool net show` lists honk's `lan_ingress` and `lan_egress` programs (their `_l2` or `_l3` variant) on every bound interface that exists. A degraded interface binding shows there as a missing program.

### D7. Fixes in honk, mechanism first

Each fix is a patch in `feed/net/honk/patches`, `Upstream-Status: Pending`, with a write-up in `docs/patches.md`, made only after the mechanism is shown on the emulator (kprobes on the `ci` image, honk's debug log):

- **#456**: reproduce LAN-to-router IPv4 TCP on br-lan (SSH, LuCI, SMB) with honk on the LAN; find why the accepted child carries no published proof and fix the proof path.
- **#476**: reproduce a reload on the emulator; find why the NFQUEUE listener reads a message of type 2 (`NLMSG_ERROR`) across the reload and fix its handling so that a reload never ends the process.
- **Offline check**: `honk-core check -c <file>` parses and admits a configuration as a start would, without touching the system or binding anything, and exits nonzero naming the reason; config-push (on the router, where honk's own build is) and the init script use it. A start, like a reload, runs without a required geodata file it does not find (its rules match nothing until the file is fetched), where the native API refuses a candidate for it; the check admits as a start does, with a warning, or the init would refuse every boot that comes before the first geodata update.
- **build.rs**: the prebuilt object through an environment variable (D2).

### D8. The native API: token mode, LAN only, no writes

honk is built without its `clash-api` feature (features `ebpf`, `native-ui`, `jemalloc`, `rprx`), so there is no Clash API to enable. The image's template keeps `experimental.native_api` off. config-push rejects a configuration that enables it without a static `secret`, or with `password_auth`, `allow_anonymous_loopback` or `config_write`. honk listens where the configuration says; fw4's zone policies already reject input from wan, podman and tailscale, so only the LAN reaches it. In LuCI, the doona switch writes a token-mode block with a random token it shows once, and the "store db" switch goes (`patches/daeuniverse`, `Inappropriate [policy: token-only native API]`). Password mode is left out because its first visitor creates the administrator.

### D9. Marks and the NFQUEUE table are registered

`config/marks.tsv` lists honk's four bits under owner `honk`; they overlap neither einat's 0x20000000 nor Tailscale's 0x00ff0000. Tailscale's policy rules mask with 0xff0000, inside the 0x3fffffff honk leaves to others. A test shows `inet honk_nfqueue` unchanged through `fw4 reload` and gone after honk stops.

### D10. Kernel and packages

Packages: `kmod-nft-queue`, `kmod-nfnetlink-queue`, `kmod-veth`, `kmod-sched-core`, `kmod-sched-bpf`, `libstdcpp`. The kernel already has BTF, cgroup BPF, tcx and netkit (`config/kernel.seed`, `config/kernel.config`). `vmlinux-btf` from daeuniverse's feed is not needed.

### D11. The private configuration moves by hand

No firmware code migrates. The user moves `dae/` to `honk/` in the private repository and checks the configuration with `honk-core check` on the router (or a push, which validates). honk's dialect differs where a dae configuration may rely on it:
- `pname()` matches a substring anywhere in the name, dae the whole name (honk #453).
- `t`/`y` read as false; `so_mark_from_dae` reads as hex; `direct(mark: 010)` is decimal.
- One declaration per line; no `/* */` comments; a `#` glued to a value is data.
- Node schemes other than ss, vmess (TCP), vless, trojan, anytls, hysteria/hysteria2, tuic, juicity and socks reject the whole configuration; in a chain `a -> b` only `a` is read.
- Group policies `random` and `min` become selector; `fixed(N)` loses its index; a group and a node cannot share a name.
- `file://` subscriptions are unsupported; subscriptions refresh daily by default.
- `global` keys honk accepts and ignores: `allow_insecure`, `sniffing_timeout`, `utls_imitate`, `tls_fragment*`, `mptcp`, `fallback_resolver`, `bandwidth_max_*`, `auto_config_kernel_parameter`.

### D12. Supply chain

`docs/supply-chain/honk.md`, as `dae.md` was: the forks of boring-sys and quinn (fork point, diff size, authorship, security-relevant changes, the pins), the crate set (advisories, licences), doona's dependencies (lockfile integrity, licences), bpf-linker's, and the conditions and re-checks for each upgrade. `dae.md` goes with dae.

## Risks / Trade-offs

- [honk is a prerelease that changes every few days] → The version is pinned in `feed/net/honk/Makefile` and moves only with the full suites; the patches are small and meant for upstream, so they shrink as upstream takes them.
- [One maintainer's forks carry TLS and QUIC] → The review (D12) and git revisions pinned in Cargo.lock; the build never relaxes cargo's checks.
- [`RUSTC_BOOTSTRAP` on a stable rustc] → It unlocks build-std only; a rustc whose `core` does not build for `bpfel-unknown-none` fails the build, not the router.
- [The #456 fix touches honk's TCP admission] → The fix waits for the mechanism; the new requirement's test runs SSH, LuCI and SMB connections from the LAN for a minute.
- [The token crosses the LAN in plain HTTP] → The API answers only from the LAN; an SSH tunnel to a loopback listener remains available, as LuCI shows.
- [Containers whose resolver is a public address stay intercepted] → That is honk's transparent DNS, as for LAN clients; containers on podman's network use aardvark-dns.

## Migration Plan

1. Merge with the full suites green on both boards; the release notes name the breaking changes and D11's dialect list.
2. The user moves `dae/` to `honk/` in the private repository and fixes the configuration until honk's check accepts it.
3. Upgrade, then push: config-push writes `/etc/honk`, enables and starts honk. `/etc/dae` from before stays unused in the overlay.
4. Rollback: the A/B rollback boots the previous slot, with dae and its configuration as they were there.
