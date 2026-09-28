# Proposal

## Why

R4S 要同时负责透明代理、完全锥形 NAT 和上行 QoS。这里选择全 eBPF 数据面：dae、einat-ebpf、qosify。这样既不用给内核打 NAT 补丁，也不用维护 nftables、libnftnl、fw4 的 fullcone 补丁。

调研发现两个问题，必须在设计上规避：

1. **dae 和 einat 会互相截断。** 两者都用 tcx 把自己挂到链头（dae 在 `tc_hook_set.go`，einat 在 `aya.rs` 里用 `LinkOrder::first()`），所以谁后挂载谁先执行。dae 的 WAN 入站程序遇到 ICMP、IP 分片和非 TCP/UDP 协议时返回 `TC_ACT_OK`，这会让链上后面的程序全部不再执行，einat 就无法还原这些回程包，结果是 ping、PMTU 探测和分片 UDP 全部失效。dae 那边要求可配置优先级的 issue #944 仍未解决。
2. **einat 需要放行 WAN→LAN 的转发。** einat 不经过 netfilter 做 NAT，所以必须放行 WAN→LAN 的转发。现有的 OpenWrt 包直接放行了全部 WAN→br-lan 的 tcp/udp/icmp，上游线路上的邻居因此可以把目的地址是内网 IP 的包直接打进来。

## What Changes

- **透明代理：dae**
  - 使用 v2.1.1，不用 daed：daed 和 dae-wing 都已归档，而且 arm64 上有内存涨到 OOM 的报告。
  - 只绑定 LAN 侧的 br-lan、podman0、tailscale0，不绑定 WAN。这样 WAN 口上没有 dae 的程序，上面第 1 个问题整个消失。代价是路由器本机发起的流量走直连。
  - 通过 luci-app-dae 管理（文本编辑 + 热重载）；config.dae 的正本放在私有配置仓库。
- **DNS**
  - dnsmasq 继续负责 DHCP 和 `.lan` 主机名。
  - dnsmasq 的上游指向 dae 的 `dns.bind`（例如 `127.0.0.1:5353`），由 dae 按规则选择上游并按域名分流。
- **NAT：einat-ebpf**
  - 使用 0.1.11，挂在 pppoe-wan 上，做 NAT44 完全锥形（EIM+EIF），不做 NAT66。
  - 只用 aya 加载器。
  - 新增一个补丁：einat 还原地址时给报文打一个 mark 位。fw4 只放行带这个 mark 的 WAN→LAN 新连接。
  - TCP、UDP、ICMP 以外的协议仍由 masquerade 处理。
  - einat 使用的端口范围不能和 `ip_local_port_range` 重叠。
- **mark 位分配表**：dae 已经占用 0x100 和 0x8000000；einat、netavark、fw4 各自使用的位都要登记进来，避免冲突。
- **QoS：qosify**
  - 只在 pppoe-wan 的出方向整形，用 cake 的 nat 模式。
  - 不创建 ifb，不做入方向整形。
- **WAN**
  - PPPoE 拨号，加 MSS 钳制。
  - IPv6 用原生地址 + DHCPv6-PD 前缀下发，不做 NAT66；dae 同样代理 IPv6。
- **转发加速**：打开 fw4 的软件 flowtable，由模拟器用例确认 PPPoE 下能否命中；命中不了或者出问题就关掉。
- **挂载顺序约束**：WAN 口和 LAN 口上各个 eBPF 程序的挂载顺序和返回值约束要写成规格，并提供可检查的方法（`bpftool net show`）。
- **自有 feed 新增**
  - dae：把 ImmortalWrt 的 2.0.0 Makefile 升级到 2.1.1；Go 依赖按 `go.sum` 校验，并缓存在 `dl/`；审查 `go.mod` 里被替换成个人 fork `olicesx/outbound` 的那个依赖。
  - luci-app-dae。
  - einat-ebpf：Rust 依赖按 `Cargo.lock` 校验，并缓存在 `dl/`。
  - luci-app-einat：可选。
- **注册健康检查**：向 `r4s-ab-rollback` 的健康检查注册两项——dae 和 einat 的 BPF 程序已挂载。

## Capabilities

### New Capabilities

- `network/transparent-proxy`：dae 绑定哪些网口，代理和直连的行为，以及路由器本机流量的策略。
- `network/dns`：dnsmasq 与 dae 之间的 DNS 链路。
- `network/nat`：einat 完全锥形 NAT44、按 mark 放行、masquerade 兜底，以及端口范围。
- `network/qos`：上行 cake 整形和 DSCP 分类。
- `network/wan`：PPPoE、MSS 钳制、IPv6 前缀下发和 flowtable 转发加速。
- `network/tc-hook-order`：各 eBPF 程序在 WAN 口和 LAN 口上的挂载顺序与返回值约束，确保它们不会互相截断；以及 mark 位的分配。

### Modified Capabilities

（无。）

## Impact

- **依赖 `r4s-build-foundation` 提供的内核特性**：BTF、`BPF_EVENTS`、`CGROUP_BPF`；以及 kmod-sched-core、kmod-sched-bpf、kmod-veth、kmod-sched-cake。
- **fw4 规则变化**：WAN 区域对 tcp、udp、icmp 关闭 masquerade；新增一条按 mark 放行的转发规则。
- **构建依赖**：Go ≥ 1.26、Rust；BPF 对象用 flake 固定的宿主 clang 编译（`BPF_TOOLCHAIN_HOST`，与 `r4s-build-foundation` 一致）。
- **验证方式**：foundation 的模拟环境里补齐运营商（PPPoE、DHCPv6-PD）、互联网（探测服务、DNS、iperf3）和代理节点。六个规格的场景全部写成 `just test` 里的自动用例，包括重拨恢复、伪造入站、cake 公平性、flowtable 命中和 dae 的 conntrack 告警。
- **宿主要求**：宿主内核要有 `ppp_generic` 和 `ppp_async`，`/dev/ppp` 要对普通用户可读写，由 CI 的准备脚本和开发文档负责。
- **只留给真机的**：RK3399 上的吞吐和 A72 绑定效果；真实线路上的一次拨号和 NAT 类型冒烟。
- **已知限制**：Tailscale 的控制面和 DERP 中继流量属于本机流量，走直连，在国内可能不稳定。
