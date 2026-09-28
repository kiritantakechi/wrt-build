# Design

## Context

See proposal.md for the motivation.

**Sources checked**:
- Kernel: Linux v6.18 (6.18.52 matches it).
- OpenWrt: main `1019293`.
- dae: v2.1.1 (`dbae2e8`).
- einat-ebpf: 0.1.11 (`ba647ce`).
- qosify: `beeb87ec`.
- Every reference below was checked against the source at these versions; paths are relative to each repository.

**Order of tc-related hooks in the kernel**:
- **Receive path**: tc ingress (`net/core/dev.c:5930`) runs first, then netfilter ingress (`:5938`). The flowtable hooks into netfilter ingress.
- **Transmit path**: the order is netfilter egress (`:4697`) → tc egress (`:4705`) → queueing discipline (`:4729`).
- **tcx versus legacy clsact filters**:
  - tcx programs always run before legacy filters (`dev.c:4368-4413`).
  - Only a return of `TC_ACT_UNSPEC` (that is, `TCX_NEXT`) continues to the next program. `TC_ACT_OK`, `SHOT`, and `REDIRECT` all terminate the whole chain, and legacy filters do not run either (`include/net/tcx.h:145-159`).

**dae**:
- Uses tcx to attach itself at the head of the chain (`control/tc_hook_set.go:583-607,690-705`).
- Returns `TC_ACT_OK` on WAN ingress for ICMP, fragments, or non-TCP/UDP (`control/kern/tproxy.c`, `do_tproxy_wan_ingress`).
- Attaches WAN hooks and cgroup hooks only when `wan_interface` is configured (`control/control_plane_datapath.go:149-151`).
- The config supports `include` to merge multiple files (`config/config_merger.go:132-150`).
- It watches link changes only to track its own `dae0` (`control_plane_core.go:589-640`); it does not automatically bind LAN interfaces that appear later.
- v2.1.1 replaces the outbound dependency with the personal fork `olicesx/outbound` (`go.mod:136`).
- daed and dae-wing are both archived on GitHub.

**einat**:
- On kernels 6.6 and later it uses tcx and attaches at the head of the chain with `LinkOrder::first()` (`src/skel/einat/aya.rs:202-203`).
- Returns `TC_ACT_UNSPEC` after address translation (`src/bpf/einat.bpf.c:1880`).
- Inbound reverse translation happens in `ingress_rev_snat` (`:1786`).
- Does not mark packets (`:1322` only reads the mark for a route lookup).
- The default port range is 20000-29999.

**qosify**:
- Attaches `cls_bpf` through legacy clsact at priority `0x110` (`interface.c:222-262`).
- Always returns `TC_ACT_UNSPEC` (`qosify-bpf.c:502-554`).
- Does not need BTF.
- With `ingress 0` it does not create the shaping `ifb-<iface>`, but it still attaches the BPF classifier on ingress (`0x110`), plus 4 u32 filters (`0x111`–`0x114`) that redirect replies with source port 53 to `ifb-dns` for classification by DNS name (`interface.c:299-330`).
- `ifb-dns` is created unconditionally when qosify starts (`dns.c:414-418`).
- `ubus call qosify get_stats` reports counters per direction and DSCP class; tests rely on it to tell whether traffic "was classified".

**cake**: nat mode reads the conntrack entry attached to the packet and takes the original-direction addresses (`net/sched/sch_cake.c:574-612`). einat does not modify conntrack, so cake gets the internal addresses.

**How the flowtable transmits under PPPoE**: the pure software flowtable uses `FLOW_OFFLOAD_XMIT_NEIGH`, which hands the packet to pppoe-wan itself to send, so it passes through pppoe-wan's tc egress (`net/netfilter/nft_flow_offload.c:95-175`; `nf_flow_table_ip.c:455-461`). It transmits directly only when the path contains a bridge or hardware offload is enabled.

**ifb**: packets returned from an ifb carry the `tc_skip_classify` flag and skip tcx, clsact, and netfilter ingress. DNS replies returned through `ifb-dns` have already been processed by einat before that, so the skip has no effect.

**Verification environment**: the foundation's emulation environment (shipped image, R4S board identity, rootless network sandbox) and test framework. This change adds the ISP and the internet on its `isp` side (D11).

## Goals / Non-Goals

**Goals:**
- The execution order of programs on the WAN and LAN ports must be guaranteed by kernel semantics and structural design, not by startup order.
- If any datapath component stops, the network must fall back to a working direct or masquerade state, never lose connectivity.
- Change upstream as little as possible: einat gets only one upstreamable mark patch, and dae is not patched.

**Non-Goals:**
- Proxying router-originated traffic.
- NAT66.
- Ingress shaping.
- Hardware offload.
- Shipping sing-box or daed in the firmware.

## Decisions

### D1. Hook layout: dae binds LAN only

```
LAN: br-lan (+ podman0, tailscale0)        WAN: pppoe-wan

 tc-in  [TCX] dae                           tc-in  [TCX] einat ingress_rev_snat (+mark)
 tc-eg  [TCX] dae                                  [cls 0x110] qosify
                                                   [u32 0x111-0x114] qosify sport 53 -> ifb-dns
                                            tc-eg  [TCX] einat egress_snat
                                                   [cls 0x110] qosify
                                            root   cake (egress only, no ifb)
```

- **How the order is guaranteed**: on the WAN port, einat uses tcx and qosify uses a legacy filter. The kernel guarantees that tcx runs first, so einat always runs before qosify, regardless of which starts first. On the LAN port, dae is the only program, so ordering is not an issue.
- **dae returning `TC_ACT_OK` on the LAN port is harmless**: there are no other programs on the LAN port, so terminating the chain cuts nothing off.
- **Alternatives**:
  - dae also binds WAN. Rejected: dae and einat would compete for the head of the chain, and dae returning `TC_ACT_OK` would cut off einat's reverse translation of ICMP and fragments; fixing that would require patching dae and guaranteeing the attach order.
  - Order by legacy filter priority. Rejected: dae and einat both prefer tcx, so both codebases would need changes.

### D2. einat mark patch

- **Patch contents**:
  - In `ingress_rev_snat`, after a packet is successfully reverse-translated to an internal address, execute `skb->mark |= inbound_mark`.
  - `inbound_mark` is set through config and a command-line argument (for example `--inbound-mark`) and passed into the program as a BPF global read-only variable; the default is 0, meaning no marking.
  - Hairpin packets are not marked.
- **Rationale**: netfilter runs after einat, and only einat itself knows which packets it reverse-translated. With the mark in place, fw4 needs only one accept rule that matches on the mark.
- **Upstreaming**: the patch does not change behavior by default, so it is suitable for upstream. Submission materials go in `docs/upstream/`; whether and when to submit is up to the repository owner.
- **Alternatives**:
  - Keep the accept-all rule. Rejected: it is a security hole.
  - Attach another tcx program in front of einat for anti-spoofing. Rejected: it brings back the ordering problem of "two programs that both must run first".

### D3. fw4 rules follow einat's lifecycle

einat's init script injects rules through procd firewall data (following the muink package's approach, changing only the WAN→LAN accept-all into accept-by-mark):

```
nat  : src wan, family ipv4, proto tcp udp icmp, target ACCEPT   # bypass masquerade
rule : src wan, dest lan, family ipv4, mark 0x20000000/0x20000000, target ACCEPT
zone wan: masq 1, mtu_fix 1        (static, from uci-defaults)
defaults: flow_offloading 1        (static)
```

- **Effect**: when einat stops, procd withdraws the two rules it injected. TCP, UDP, and ICMP automatically fall back to masquerade, and the inbound accept-by-mark rule disappears with them, which satisfies the nat spec requirement "Fall back to masquerade when einat stops".
- **Other protocols**: ESP, GRE, and the like are not affected by the nat ACCEPT rule and always go through masquerade.

### D4. Mark bit allocation table

There is a single allocation table: `config/marks.tsv`. GitHub renders TSV directly as a table, so no separate document is generated. Initial contents:

```
mask         owner      purpose                                   source
0x00000100   dae        dae own sockets (internal)                common/utils.go:357
0x08000000   dae        dae0peer -> table 2023 (internal)         netns_utils.go
0x20000000   einat      reverse-translated inbound (our patch)    D2
0x00ff0000   tailscale  0x40000 masq, 0x80000 bypass              to confirm in r4s-services
```

`scripts/marks-check.sh` is called by `just check`. It reads the allocation table, scans the marks that appear in each component's config templates under `files/` and `feed/`, and fails when a bit is unregistered or overlapping. In the services design netavark installs no firewall rules and uses no marks, so it is not in the table.

### D5. dae packaging and config layout

- **Packaging**:
  - Start from ImmortalWrt's `net/dae` Makefile (2.0.0), upgrade it to 2.1.1, and keep the `trace` build tag.
  - Compile the BPF objects with the host clang pinned by the foundation (`BPF_TOOLCHAIN_HOST`).
  - Verify Go modules against `go.sum` and cache them in `dl/`.
- **Why not vendor everything**: `go.sum` and `Cargo.lock` already pin the hash of every dependency, so integrity is assured; vendoring everything would also require hosting the source tarballs separately, which adds burden. This decision has been synced to the proposal.
- **Config layout**:

```
/etc/dae/config.dae            (image)  include { generated/*.dae  user/*.dae }
/etc/dae/generated/10-bind.dae (init)   global { lan_interface: <br-lan[,podman0][,tailscale0]>
                                                 auto_config_kernel_parameter: true }
                                        dns { bind: 127.0.0.1:5353 }
/etc/dae/user/*.dae            (pushed from private config repo; nodes, groups, routing, dns upstreams)
```

  - The `generated/` directory holds fragments generated by the init script; user config MUST NOT contain `lan_interface` or `wan_interface`. The push tool checks this before pushing.
- **Interfaces that appear later**: a hotplug script (for the `net` subsystem) watches podman0 and tailscale0 appear and disappear, regenerates `10-bind.dae` accordingly, and then runs `dae reload`, which satisfies "bound within 60 seconds".
- **CPU pinning**: the init script supports an optional `taskset` parameter that pins dae to the A72 big cores (cpu4-5), off by default. The RK3399 device tree gives the A72s a higher `capacity-dmips-mhz`, so the scheduler already moves busy threads onto the big cores, while pinning would cap the Go runtime at two threads. Throughput is not measured (D11), so the scheduler's choice stays the default.
- **Alternatives**: users write `lan_interface` in their own config. Rejected: this cannot handle interfaces that appear later.

### D6. einat packaging

- **Approach**: start from muink's `openwrt-einat-ebpf` (0.1.11).
  - cargo enables only the aya loader, not the libbpf backend (which needs bindgen and host libclang on aarch64), and not the `ipv6` feature.
  - `build.rs` calls `clang -target bpfel` from PATH directly; the flake-provided clang is already in PATH.
  - Verify Rust dependencies against `Cargo.lock`.
- **Port range**: einat uses 20000-29999; local ephemeral ports stay at the kernel default of 32768-60999, so the two do not overlap.

### D7. DNS

- **dnsmasq settings**: `server=127.0.0.1#5353`, ordered before the upstreams obtained from WAN, with `strictorder` enabled, so dae is always tried first when it is available.
- **When dae is unavailable**: UDP queries to 5353 get port unreachable, and dnsmasq moves on to the next upstream, which satisfies "fall back to upstream DNS".
- **Not exposed**: dae's `dns.bind` binds only to 127.0.0.1.
- **Alternatives**: `noresolv` with dae as the only upstream. Rejected: if dae stops, the LAN cannot resolve names.

### D8. qosify

- **UCI settings**: `interface wan` is set to `ingress 0`, `egress 1`, `bandwidth_up <95% of measured upload bandwidth>`, `mode diffserv4`, `nat 1`, `host_isolate 1`.
- **Encapsulation overhead**: `overhead_type` is set for "fiber + PPPoE over Ethernet".
- **Classification rules**: keep qosify's default classification rules, plus port rules for gaming and video conferencing.

### D9. WAN and IPv6

- **WAN**: uci-defaults generates a WAN config without credentials: `proto pppoe`, `device eth0`, `ipv6 auto`. Credentials are written by the config push tool from `r4s-release-pipeline`.
- **LAN**: `ip6assign 64`; odhcpd provides both RA and DHCPv6.
- **How uci-defaults writes**: it writes an option only when that option is not yet set, so config-preserving upgrades do not overwrite it.

### D10. Health check registration

- **`/etc/healthcheck.d/50-dae`**: the dae process is running, and `bpftool net show` shows dae programs attached to br-lan (and to podman0 and tailscale0 when they currently exist).
- **`/etc/healthcheck.d/50-einat`**: the einat process is running; when pppoe-wan exists, einat is on both its tcx ingress and egress. When pppoe-wan does not exist, the check passes.
- **Dependency**: the image must include `bpftool-minimal`.

### D11. Verification: emulating the ISP and the internet in the sandbox

```
client-a ─┐                                                     ┌─ inet   203.0.113.0/24  2001:db8:ffff::/64
client-b ─┼─ br-lan ─ eth1 │ R4S image │ eth0 ─ br-wan ─ isp ─ br-inet ─┤        probes, dns, iperf3
runner   ─┘ 10.0.0.0/24    │  (QEMU)   │  PPPoE          (BRAS)        └─ proxy  198.51.100.53  2001:db8:53::53
                                                                                 socks5 exit
isp:  pppoe-server (user mode, pty + ppp_async)  pool 192.0.2.64-127, next address on every redial
      per session (ip-up / ipv6-up): radvd + kea-dhcp6, PD /56 out of 2001:db8:100::/40
      pppd ms-dns 203.0.113.53, mtu 1492
inet: netprobe (udp/tcp whoami: peer addr+port, TCP_MAXSEG; "big" mode = 3000-byte UDP reply)
      dnsmasq authoritative for example.test, iperf3 servers
proxy: microsocks, outbound bound to its own addresses
```

- **Addresses**: all from documentation-reserved ranges (RFC 5737, RFC 3849), so they cannot clash with real networks.
- **Tools**: rp-pppoe, ppp, kea, radvd, dnsmasq, microsocks, iperf3, and iputils all come from the pinned nixpkgs and are added to the flake's test tool group.
- **`netprobe`**: `wrt_tests/netprobe.py` is a small asyncio service that echoes the peer's address and port and the MSS it sees. The full-cone, spoofed-inbound, local-port, source-address, MSS, and fragmentation checks all rely on it. For ESP it sends and receives protocol 50 packets over raw sockets, without depending on the host's xfrm.
- **Host requirements**: the host kernel must have `ppp_generic` and `ppp_async` (OrbStack and GitHub runners both do; the OrbStack kernel has no `pppoe.ko`, so the ISP side uses rp-pppoe's user mode), and `/dev/ppp` must be readable and writable by regular users. CI's `prepare-runner.sh` and `docs/dev-setup.md` take care of both; `env-report` checks them. The router-side PPPoE runs inside the QEMU VM and does not depend on the host.
- **Tests map one-to-one to specs**: `tests/network/` has six test modules named after the six specs: `test_transparent_proxy`, `test_dns`, `test_nat`, `test_qos`, `test_wan`, `test_tc_hook_order`. Each module boots the emulator once; between tests only the config is reset, with no reboot.
- **Representative techniques**:
  - Spoofed inbound: the ISP side routes 10.0.0.0/24 into the PPP session, and also injects frames whose destination IP is an internal address directly on the layer 2 segment of eth0. Both paths must be dropped.
  - Redial: the ISP side ends the session; the router redials and gets a new address.
  - Fairness: the tests set qosify's upload bandwidth to 20 Mbit/s, which TCG can saturate, so the result does not depend on line rate.
  - flowtable: read the `[OFFLOAD]` flag from `conntrack -L`, and cross-check the source address with `netprobe`.
  - dae's conntrack warning (issue #848): check dmesg in the emulator. The kernel is the same, so the result carries over directly.
- **Not verified** (no step needs the device):
  1. Throughput: TCG says nothing about RK3399 rates, and no requirement states one. The fairness test uses a bandwidth TCG can saturate instead.
  2. A real ISP line: the emulated ISP uses common values (PPPoE with MTU 1492, a /56 PD, LCP echo), and full-cone behavior is checked with `netprobe` from the emulated internet. A different line changes only configuration values, which the pushed config sets.

## Risks / Trade-offs

- **[conntrack warning when dae creates a network namespace]** issue #848 was reported on 6.6. → An emulator test checks dmesg; if the warning still appears on 6.18, follow up on an upstream fix.
- **[Ingress misses the flowtable under PPPoE]** If fw4 also registers the lower eth0 in the flowtable, the ingress lookup happens before einat reverse-translates the address and misses, so return traffic can only take the slow path. → An emulator test reads the conntrack offload flag and records whether each direction hits. The result affects only performance, not correctness.
- **[include merge semantics differ from expectations]** → Verify with an emulator test first during implementation; if it does not hold, have the init script concatenate the fragments as text into one complete config file instead.
- **[dae depends on a personal fork of outbound]** → Pin it to the version in `go.sum` and review its diff against upstream `daeuniverse/outbound` (task 1.2); review again on every later dae upgrade.
- **[The Rust host toolchain lengthens CI cold starts]** → It is already in the toolchain stage of the foundation design, and it is cached.
- **[dae has a memory peak of about 120 MB at load]** Acceptable with 4 GB of RAM.
- **[Tailscale's control plane goes direct]** This is a known limitation, recorded in the proposal.
- **[The emulated ISP behaves differently from a real ISP]** For example PD length, MTU, and the LCP echo interval. → The emulation uses common values, and nothing checks a real line. The differences affect only configuration values, which the pushed config sets, not the structure of the datapath.
- **[The host lacks ppp support]** → `env-report` reports the error early along with the fix, instead of failing only when the tests run.

## Migration Plan

- **Deployment order**:
  1. Deploy einat, qosify, and the fw4 rules first, with dae not yet enabled, and verify NAT and QoS.
  2. Then push the dae config and enable dae.
- **Rollback**: stopping any component falls back to direct or masquerade, so no extra rollback steps are needed. For serious problems, use A/B to switch back to the previous slot.

## Open Questions

- The exact upload bandwidth has to be measured; it affects only one qosify config value.
