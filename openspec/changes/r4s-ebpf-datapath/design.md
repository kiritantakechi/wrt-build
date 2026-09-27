# Design

## Context

动机见 proposal.md。

**核对依据**：
- 内核：Linux v6.18（6.18.52 与其一致）。
- OpenWrt：main `1019293`。
- dae：v2.1.1（`dbae2e8`）。
- einat-ebpf：0.1.11（`ba647ce`）。
- qosify：`beeb87ec`。
- 下面引用都在这些版本的源码里核对过，路径相对于各自的仓库。

**内核里 tc 相关钩子的执行顺序**：
- **收包路径**：先执行 tc 入口（`net/core/dev.c:5930`），再执行 netfilter 入口（`:5938`）。flowtable 就挂在 netfilter 入口上。
- **发包路径**：顺序是 netfilter 出口（`:4697`）→ tc 出口（`:4705`）→ 队列规则（`:4729`）。
- **tcx 与传统 clsact 过滤器的关系**：
  - tcx 程序总是先于传统过滤器执行（`dev.c:4368-4413`）。
  - 只有返回 `TC_ACT_UNSPEC`（也就是 `TCX_NEXT`）才会继续执行下一个程序。`TC_ACT_OK`、`SHOT`、`REDIRECT` 都会终止整条链，传统过滤器也不再执行（`include/net/tcx.h:145-159`）。

**dae**：
- 用 tcx 把自己挂到链头（`control/tc_hook_set.go:583-607,690-705`）。
- WAN 入站遇到 ICMP、分片或非 TCP/UDP 时返回 `TC_ACT_OK`（`control/kern/tproxy.c`，`do_tproxy_wan_ingress`）。
- 只有配置了 `wan_interface` 时，才会挂 WAN 钩子和 cgroup 钩子（`control/control_plane_datapath.go:149-151`）。
- 配置支持 `include` 合并多个文件（`config/config_merger.go:132-150`）。
- 它监听网卡变化只是为了跟踪自己的 `dae0`（`control_plane_core.go:589-640`），不会自动绑定后来出现的 LAN 接口。
- v2.1.1 把 outbound 这个依赖替换成了个人 fork `olicesx/outbound`（`go.mod:136`）。
- daed 和 dae-wing 在 GitHub 上都已归档。

**einat**：
- 在 6.6 以上的内核上用 tcx，并以 `LinkOrder::first()` 挂到链头（`src/skel/einat/aya.rs:202-203`）。
- 地址转换完成后返回 `TC_ACT_UNSPEC`（`src/bpf/einat.bpf.c:1880`）。
- 入站还原地址在 `ingress_rev_snat`（`:1786`）里完成。
- 不给报文打 mark（`:1322` 只是读 mark 去做路由查询）。
- 默认端口范围是 20000-29999。

**qosify**：
- 用传统 clsact 挂 `cls_bpf`，优先级 `0x110`（`interface.c:222-262`）。
- 永远返回 `TC_ACT_UNSPEC`（`qosify-bpf.c:502-554`）。
- 不需要 BTF。
- `ingress 0` 时不建 ifb。

**cake**：nat 模式会读报文上挂着的 conntrack 记录，取原始方向的地址（`net/sched/sch_cake.c:574-612`）。einat 不改 conntrack，所以取到的是内网地址。

**flowtable 在 PPPoE 下的发送方式**：纯软件 flowtable 走 `FLOW_OFFLOAD_XMIT_NEIGH`，也就是交给 pppoe-wan 本身去发，因此会经过 pppoe-wan 的 tc 出口（`net/netfilter/nft_flow_offload.c:95-175`；`nf_flow_table_ip.c:455-461`）。只有路径里有网桥，或者开了硬件卸载时，才会直接发。

**ifb**：从 ifb 转回来的报文带着 `tc_skip_classify` 标记，会跳过 tcx、clsact 和 netfilter 入口。

## Goals / Non-Goals

**Goals:**
- WAN 口和 LAN 口上程序的执行顺序，要靠内核语义和结构设计来保证，不能依赖启动先后。
- 任何一个数据面组件停掉，网络都要回落到可用的直连或 masquerade 状态，不能断网。
- 尽量少改上游：einat 只加一个可以提交给上游的 mark 补丁，dae 不打补丁。

**Non-Goals:**
- 代理路由器本机的流量。
- NAT66。
- 入方向整形。
- 硬件卸载。
- 在固件里带 sing-box 或 daed。

## Decisions

### D1. 钩子布局：dae 只绑 LAN

```
LAN: br-lan (+ podman0, tailscale0)        WAN: pppoe-wan

 tc-in  [TCX] dae                           tc-in  [TCX] einat ingress_rev_snat (+mark)
 tc-eg  [TCX] dae                                  [cls 0x110] qosify
                                            tc-eg  [TCX] einat egress_snat
                                                   [cls 0x110] qosify
                                            root   cake (egress only, no ifb)
```

- **执行顺序怎么保证**：WAN 口上 einat 用的是 tcx，qosify 用的是传统过滤器。内核保证 tcx 先执行，所以 einat 总在 qosify 前面，和谁先启动无关。LAN 口上只有 dae 一个程序，不存在顺序问题。
- **dae 在 LAN 口返回 `TC_ACT_OK` 没有影响**：LAN 口上没有别的程序，终止了也不会截断谁。
- **备选方案**：
  - dae 也绑 WAN。否决，因为 dae 和 einat 会互相抢链头，dae 返回 `TC_ACT_OK` 会截断 einat 对 ICMP 和分片的还原；要解决就得给 dae 打补丁，并且保证挂载顺序。
  - 用传统过滤器的优先级来排序。否决，因为 dae 和 einat 都优先使用 tcx，需要改两边的代码。

### D2. einat 的 mark 补丁

- **补丁内容**：
  - 在 `ingress_rev_snat` 里，报文被成功还原成内网地址之后，执行 `skb->mark |= inbound_mark`。
  - `inbound_mark` 通过配置和命令行参数设置（例如 `--inbound-mark`），经 BPF 全局只读变量传进程序；默认值为 0，表示不打标。
  - 发夹转发（hairpin）的报文不打标。
- **理由**：netfilter 在 einat 之后执行，只有 einat 自己知道哪个报文是它还原的。打标后，fw4 只需要一条按 mark 匹配的放行规则。
- **提交上游**：补丁默认不改变行为，可以提交给上游。
- **备选方案**：
  - 沿用全放行规则。否决，有安全漏洞。
  - 在 einat 前面再挂一个 tcx 程序做防伪造。否决，又会回到“两个程序都要排在最前面”的顺序问题。

### D3. fw4 规则跟随 einat 的生命周期

einat 的 init 脚本通过 procd 的防火墙数据注入规则（沿用 muink 包的做法，只把 WAN→LAN 的全放行改为按 mark 放行）：

```
nat  : src wan, family ipv4, proto tcp udp icmp, target ACCEPT   # bypass masquerade
rule : src wan, dest lan, family ipv4, mark 0x20000000/0x20000000, target ACCEPT
zone wan: masq 1, mtu_fix 1        (static, from uci-defaults)
defaults: flow_offloading 1        (static)
```

- **效果**：einat 停止时，procd 会撤掉它注入的两条规则。TCP、UDP、ICMP 自动回落到 masquerade，入站的按 mark 放行规则也随之消失，满足 nat 规格里“停止时回落到 masquerade”那一条。
- **其他协议**：ESP、GRE 等不受 nat ACCEPT 规则影响，始终走 masquerade。

### D4. mark 位分配表

仓库里维护一份机器可读的 `config/marks.tsv` 作为分配表，同时生成可读版本 `docs/mark-registry.md`。初始内容：

```
mask         owner      purpose                                   source
0x00000100   dae        dae own sockets (internal)                common/utils.go:357
0x08000000   dae        dae0peer -> table 2023 (internal)         netns_utils.go
0x20000000   einat      reverse-translated inbound (our patch)    D2
0x00ff0000   tailscale  0x40000 masq, 0x80000 bypass              to confirm in r4s-services
(tbd)        netavark   podman firewall                           to confirm in r4s-services
```

`scripts/lint-marks.sh`（对应 `just lint`）读取分配表，扫描 `files/` 和 `feed/` 里各组件的配置模板中出现的 mark。出现未登记或重叠的位时，检查失败。

### D5. dae 的打包与配置结构

- **打包**：
  - 以 ImmortalWrt 的 `net/dae` Makefile（2.0.0）为起点，升级到 2.1.1，保留 `trace` 构建标签。
  - BPF 对象用 foundation 固定的宿主 clang 编译（`BPF_TOOLCHAIN_HOST`）。
  - Go 模块按 `go.sum` 校验，并缓存在 `dl/`。
- **为什么不整体 vendor**：`go.sum` 和 `Cargo.lock` 已经固定了每个依赖的哈希，完整性有保障；整体 vendor 还得另外托管源码包，增加负担。这个决定已经同步到 proposal。
- **配置结构**：

```
/etc/dae/config.dae            (image)  include { generated/*.dae  user/*.dae }
/etc/dae/generated/10-bind.dae (init)   global { lan_interface: <br-lan[,podman0][,tailscale0]>
                                                 auto_config_kernel_parameter: true }
                                        dns { bind: 127.0.0.1:5353 }
/etc/dae/user/*.dae            (pushed from private config repo; nodes, groups, routing, dns upstreams)
```

  - `generated/` 目录里是 init 脚本生成的片段，用户配置里 MUST NOT 出现 `lan_interface` 或 `wan_interface`。推送工具在推送前会检查这一点。
- **后出现的接口怎么处理**：一个 hotplug 脚本（对应 `net` 子系统）监听 podman0 和 tailscale0 的出现与消失，据此重新生成 `10-bind.dae`，然后执行 `dae reload`，满足“60 秒内完成绑定”。
- **CPU 绑定**：init 脚本支持可选的 `taskset` 参数，把 dae 绑到 A72 大核（cpu4-5）。默认值由 9.9 的实测结果决定。
- **备选方案**：用户配置里自己写 `lan_interface`。否决，因为这样无法处理后来才出现的接口。

### D6. einat 的打包

- **做法**：以 muink 的 `openwrt-einat-ebpf`（0.1.11）为起点。
  - cargo 只启用 aya 加载器，不启用 libbpf 后端（在 aarch64 上它需要 bindgen 和宿主 libclang），也不启用 `ipv6` 特性。
  - `build.rs` 会直接调用 PATH 里的 `clang -target bpfel`，flake 提供的 clang 已经在 PATH 里。
  - Rust 依赖按 `Cargo.lock` 校验。
- **端口范围**：einat 用 20000-29999；本机临时端口保持内核默认的 32768-60999，互不重叠。

### D7. DNS

- **dnsmasq 的设置**：`server=127.0.0.1#5353`，排在 WAN 获得的上游之前，并打开 `strictorder`，这样 dae 可用时总是先走 dae。
- **dae 不可用时**：发往 5353 的 UDP 查询会收到端口不可达，dnsmasq 就转向下一个上游，满足“回落到上游 DNS”。
- **不对外暴露**：dae 的 `dns.bind` 只绑在 127.0.0.1。
- **备选方案**：`noresolv` 加上只用 dae 一个上游。否决，因为 dae 停了 LAN 就无法解析。

### D8. qosify

- **UCI 设置**：`interface wan` 的设置为 `ingress 0`、`egress 1`、`bandwidth_up <实测上行带宽的 95%>`、`mode diffserv4`、`nat 1`、`host_isolate 1`。
- **封装开销**：`overhead_type` 按“光纤 + PPPoE over Ethernet”设置。
- **分类规则**：沿用 qosify 默认的分类规则，另加游戏和视频会议的端口规则。

### D9. WAN 和 IPv6

- **WAN**：用 uci-defaults 生成不含凭据的 WAN 配置：`proto pppoe`、`device eth0`、`ipv6 auto`。凭据由 `r4s-release-pipeline` 的配置推送工具写入。
- **LAN**：`ip6assign 64`，odhcpd 同时提供 RA 和 DHCPv6。
- **uci-defaults 的写法**：只在对应选项尚未设置时写入，这样保留配置升级时不会覆盖。

### D10. 健康检查注册

- **`/etc/healthcheck.d/50-dae`**：dae 进程在运行，并且 `bpftool net show` 显示 br-lan（以及当前存在的 podman0、tailscale0）上都挂着 dae 的程序。
- **`/etc/healthcheck.d/50-einat`**：einat 进程在运行；pppoe-wan 存在时，它的 tcx 入口和出口上都有 einat。pppoe-wan 不存在时直接判为通过。
- **依赖**：镜像里要带上 `bpftool-minimal`。

## Risks / Trade-offs

- **[dae 创建网络命名空间时触发 conntrack 告警]** issue #848 是在 6.6 上报的。→ 上机时检查 dmesg；如果 6.18 上仍然出现，就跟进上游修复。
- **[PPPoE 下入方向命中不了 flowtable]** 如果 fw4 把下层的 eth0 也注册进 flowtable，入方向的查表会发生在 einat 还原地址之前，查不中，回程就只能走慢路径。→ 用 `nft list flowtables` 和 conntrack 的加速标记实测。结果只影响性能，不影响正确性。
- **[include 合并的语义和预期不一致]** → 实施时先做验证；如果不满足，就改为由 init 脚本把几个片段按文本拼接成一个完整配置文件。
- **[dae 依赖的 outbound 个人 fork]** → 固定到 `go.sum` 里的版本，并审查它和上游 `daeuniverse/outbound` 的差异（任务 1.2）；以后 dae 升级时重新审查。
- **[Rust 宿主工具链会拉长 CI 的冷启动]** → 它已经在 foundation 设计的工具链阶段里，并被缓存。
- **[dae 加载时有大约 120 MB 的内存峰值]** 4 GB 内存下可以接受。
- **[Tailscale 控制面走直连]** 这是已知限制，已记录在 proposal 里。

## Migration Plan

- **部署顺序**：
  1. 先部署 einat、qosify 和 fw4 规则，这时 dae 不启用，验证 NAT 和 QoS。
  2. 再推送 dae 配置并启用 dae。
- **回退**：停掉任何一个组件都会回落到直连或 masquerade，不需要额外的回退步骤。发生严重问题时，用 A/B 切回上一个槽位。

## Open Questions

- 上行带宽的具体数值要实测，只影响 qosify 的一个配置值。
- 是否要把 dae 绑到 A72，由 9.9 的实测决定，只影响 init 脚本的一个默认参数。
