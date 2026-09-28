# Proposal

## Why

The R4S must handle transparent proxying, full-cone NAT, and upload QoS at the same time. We choose an all-eBPF datapath: dae, einat-ebpf, and qosify. This avoids patching the kernel for NAT and avoids maintaining fullcone patches for nftables, libnftnl, and fw4.

Research surfaced two problems that the design must avoid:

1. **dae and einat cut each other off.** Both use tcx to attach themselves at the head of the chain (dae in `tc_hook_set.go`, einat in `aya.rs` via `LinkOrder::first()`), so whichever attaches last runs first. dae's WAN ingress program returns `TC_ACT_OK` for ICMP, IP fragments, and non-TCP/UDP protocols, which stops every later program in the chain from running. einat then cannot reverse-translate these return packets, and ping, PMTU discovery, and fragmented UDP all break. dae's issue #944, which asks for a configurable priority, is still open.
2. **einat needs WAN→LAN forwarding to be accepted.** einat does NAT without netfilter, so WAN→LAN forwarding must be accepted. The existing OpenWrt package simply accepts all WAN→br-lan tcp/udp/icmp, so neighbors on the upstream link can send packets addressed to internal IPs straight in.

## What Changes

- **Transparent proxy: dae**
  - Use v2.1.1, not daed: daed and dae-wing are both archived, and there are reports of memory growing until OOM on arm64.
  - Bind only the LAN-side br-lan, podman0, and tailscale0, not WAN. With no dae program on the WAN port, problem 1 above disappears entirely. The cost is that router-originated traffic goes direct.
  - Manage it through luci-app-dae (text editing + hot reload); the canonical copy of config.dae lives in the private config repository.
- **DNS**
  - dnsmasq keeps handling DHCP and `.lan` hostnames.
  - dnsmasq's upstream points at dae's `dns.bind` (for example `127.0.0.1:5353`); dae selects upstreams by rule and splits by domain.
- **NAT: einat-ebpf**
  - Use 0.1.11, attached to pppoe-wan, doing full-cone NAT44 (EIM+EIF), no NAT66.
  - Use only the aya loader.
  - Add one patch: einat sets a mark bit on packets it reverse-translates. fw4 accepts only new WAN→LAN connections that carry this mark.
  - Protocols other than TCP, UDP, and ICMP are still handled by masquerade.
  - einat's port range must not overlap `ip_local_port_range`.
- **Mark bit allocation table**: dae already uses 0x100 and 0x8000000; the bits used by einat, netavark, and fw4 must all be registered here to avoid conflicts.
- **QoS: qosify**
  - Shape only pppoe-wan egress, using cake in nat mode.
  - No ifb, no ingress shaping.
- **WAN**
  - PPPoE dial-up, with MSS clamping.
  - IPv6 uses native addresses + DHCPv6-PD prefix delegation, no NAT66; dae proxies IPv6 too.
- **Forwarding acceleration**: enable fw4's software flowtable; an emulator test confirms whether it hits under PPPoE; if it does not hit or causes problems, turn it off.
- **Attach-order constraints**: the attach order and return-value constraints of each eBPF program on the WAN and LAN ports are written as a spec, with a checkable method (`bpftool net show`).
- **Additions to our own feed**
  - dae: upgrade ImmortalWrt's 2.0.0 Makefile to 2.1.1; verify Go dependencies against `go.sum` and cache them in `dl/`; review the dependency in `go.mod` that is replaced by the personal fork `olicesx/outbound`.
  - luci-app-dae.
  - einat-ebpf: verify Rust dependencies against `Cargo.lock` and cache them in `dl/`.
  - luci-app-einat: optional.
- **Health check registration**: register two checks with the `r4s-ab-rollback` health check: dae's and einat's BPF programs are attached.

## Capabilities

### New Capabilities

- `network/transparent-proxy`: which interfaces dae binds, proxy and direct behavior, and the policy for router-originated traffic.
- `network/dns`: the DNS path between dnsmasq and dae.
- `network/nat`: einat full-cone NAT44, accept-by-mark, masquerade fallback, and port ranges.
- `network/qos`: upload cake shaping and DSCP classification.
- `network/wan`: PPPoE, MSS clamping, IPv6 prefix delegation, and flowtable forwarding acceleration.
- `network/tc-hook-order`: the attach order and return-value constraints of the eBPF programs on the WAN and LAN ports, so they do not cut each other off; and mark bit allocation.

### Modified Capabilities

(None.)

## Impact

- **Depends on kernel features from `r4s-build-foundation`**: BTF, `BPF_EVENTS`, `CGROUP_BPF`; plus kmod-sched-core, kmod-sched-bpf, kmod-veth, and kmod-sched-cake.
- **fw4 rule changes**: the WAN zone disables masquerade for tcp, udp, and icmp; a new forward rule accepts by mark.
- **Build dependencies**: Go ≥ 1.26, Rust; BPF objects are compiled with the flake-pinned host clang (`BPF_TOOLCHAIN_HOST`, same as `r4s-build-foundation`).
- **Verification**: the foundation's emulation environment gains an ISP (PPPoE, DHCPv6-PD), an internet (probe services, DNS, iperf3), and a proxy node. Every scenario in the six specs becomes an automated test in `just test`, including redial recovery, spoofed inbound, cake fairness, flowtable hits, and dae's conntrack warning.
- **Host requirements**: the host kernel must have `ppp_generic` and `ppp_async`, and `/dev/ppp` must be readable and writable by regular users; the CI preparation script and the developer docs take care of this.
- **Not verified**: throughput on the RK3399 and a real ISP line; no step needs the device. The emulator runs the same datapath against an emulated ISP.
- **Known limitation**: Tailscale's control plane and DERP relay traffic is router-originated traffic, goes direct, and may be unstable in China.
