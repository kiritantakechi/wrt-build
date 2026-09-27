# Tasks

## 1. 打包

- [ ] 1.1 在自有 feed 里新增 dae 2.1.1：以 ImmortalWrt 的 Makefile 为起点，BPF 用宿主 clang 编译，Go 模块按 `go.sum` 校验。验证：CI 构建成功，设备上 `dae --version` 输出 2.1.1。
- [ ] 1.2 审查 `olicesx/outbound` 在 `go.sum` 固定的那个版本与上游 `daeuniverse/outbound` 之间的差异，把结论写进 `docs/supply-chain/dae.md`。验证：文档里有差异摘要和是否接受的结论；如果结论是不接受，要先解决再继续后面的任务。
- [ ] 1.3 新增 luci-app-dae。验证：LuCI 里的 dae 页面能打开，保存配置后日志里出现热重载记录。
- [ ] 1.4 在自有 feed 里新增 einat：只用 aya 加载器，不启用 ipv6 特性，Rust 依赖按 `Cargo.lock` 校验。验证：设备上 `einat --version` 输出 0.1.11；用 `readelf -d` 查看，可执行文件不依赖 libbpf 和 libelf。
- [ ] 1.5 写 einat 的 mark 补丁（design D2），同时尝试提交给上游。验证：设置 `--inbound-mark 0x20000000` 后，fw4 按 mark 放行那条规则的计数器，会随着已映射端口的入站连接增长；不设置时行为和原来一致。补丁的 PR 链接记录进 `docs/upstream-contributions.md`。
- [ ] 1.6 新增 `config/datapath.seed`：kmod-sched-core、kmod-sched-bpf、kmod-veth、kmod-sched-cake、qosify、dae、luci-app-dae、einat、bpftool-minimal。验证：`just config ci` 的逐行校验通过。

## 2. mark 分配表

- [ ] 2.1 建立 `config/marks.tsv` 和生成出来的 `docs/mark-registry.md`，初始内容见 design D4。验证：`just lint` 生成的文档与仓库中的一致。
- [ ] 2.2 实现 `scripts/lint-marks.sh`，接进 `just lint` 和 CI。验证：在某个模板里故意写一个与 dae 重叠的 mark，检查失败并报出冲突的两方；删掉后检查通过。

## 3. WAN、防火墙与 einat 集成

- [ ] 3.1 用 uci-defaults 生成 WAN 和 LAN 的配置：PPPoE 不含凭据、`ipv6 auto`、`mtu_fix 1`、`flow_offloading 1`、`ip6assign 64`，只在选项尚未设置时写入。验证：全新安装后配置符合预期；手动修改之后做一次保留配置升级，修改的值没有被覆盖；镜像里的 PPPoE 凭据为空。
- [ ] 3.2 einat 的 init 脚本：通过 procd 注入 design D3 里的两条防火墙规则，并传入 `--inbound-mark` 和端口范围。验证：`nft list ruleset` 里有 masquerade 旁路规则和按 mark 放行的规则；停止 einat 后这两条都消失。
- [ ] 3.3 注册 `/etc/healthcheck.d/50-einat`。验证：在 A/B 健康检查的测试工具里跑三个用例——einat 没运行时判失败；einat 在运行但 pppoe-wan 不存在时判通过；pppoe-wan 存在但没挂上 einat 时判失败。

## 4. dae 集成

- [ ] 4.1 实现 design D5 的配置结构：镜像里的 `config.dae` 只负责 include；init 脚本生成 `generated/10-bind.dae`；`user/` 目录留空并提供示例。验证：先确认 include 的合并语义，把结论写进 design 的风险说明；dae 启动后 `bpftool net show dev br-lan` 能看到它的程序，pppoe-wan 上没有。
- [ ] 4.2 实现 hotplug：podman0 或 tailscale0 出现或消失时，重新生成绑定片段并执行 `dae reload`。验证：dae 运行中手动创建 podman0，60 秒内它上面出现 dae 的程序；删除后程序被移除，dae 仍在运行。
- [ ] 4.3 在 init 脚本里加入可选的 CPU 绑定参数，默认关闭。验证：打开后 `taskset -p $(pidof dae)` 显示 cpu4-5。
- [ ] 4.4 注册 `/etc/healthcheck.d/50-dae`。验证：在健康检查测试工具里，dae 没运行判失败，程序缺失判失败，正常情况判通过。

## 5. DNS

- [ ] 5.1 配置 dnsmasq：`server=127.0.0.1#5353` 排在前面，打开 `strictorder`，保留 WAN 上获得的上游；dae 的 `dns.bind` 设为 127.0.0.1:5353。验证：`<主机名>.lan` 由 dnsmasq 直接回答；外部域名出现在 dae 的日志里；从 LAN 向 10.0.0.1:5353 发查询得不到响应。
- [ ] 5.2 回落测试。验证：停止 dae 后 LAN 客户端仍能解析外部域名；重新启动 dae 后查询重新走 dae。

## 6. QoS

- [ ] 6.1 配置 qosify：只开出方向，设置上行带宽和封装开销，模式为 diffserv4 加 nat 和 host_isolate。验证：`tc qdisc show dev pppoe-wan` 显示 cake 且带宽正确；`ip link` 里没有 ifb 设备。
- [ ] 6.2 分类验证。验证：命中 voice 规则的流量在 `tc -s qdisc` 的语音档位计数里增长。

## 7. 真机验证（结果记录在 `docs/validation/datapath.md`）

- [ ] 7.1 程序顺序与返回值：检查 pppoe-wan 和 br-lan 上的程序列表；从 LAN ping 外部；用 `tracepath` 看 PMTU；接收分片的 UDP（例如 `iperf3 -u -l 3000`）。验证：程序列表符合 tc-hook-order 规格；ping 通；PMTU 正确；分片的 UDP 能完整收到，qosify 的分类计数在增长。
- [ ] 7.2 NAT 类型：在 LAN 主机上用 STUN 工具检测 NAT 类型。验证：结果是完全锥形（映射和过滤都与外部端点无关）。
- [ ] 7.3 伪造入站：在实验环境里临时把 WAN 改成 DHCP 接到一台测试机，从测试机向内网 IP 发起新连接。验证：连接被丢弃；已映射端口的入站连接被放行。
- [ ] 7.4 einat 回落与 ESP：停止 einat 后访问外网；LAN 客户端建立 IPsec 隧道。验证：停 einat 后仍能上网；ESP 报文以 WAN 地址发出，隧道建立成功。
- [ ] 7.5 重拨恢复：用 `ifdown wan && ifup wan` 重拨，重复 3 次。验证：每次都在 60 秒内恢复 einat 和 qosify 的挂载，完全锥形行为和 cake 都恢复。
- [ ] 7.6 flowtable：持续下载时查看 `nft list flowtables` 和 `conntrack -L` 里的加速标记，同时从外部核对源地址。验证：出方向被加速，源地址始终是 WAN 地址；入方向有没有命中 flowtable 记录下来，作为性能结论。
- [ ] 7.7 公平性：两台 LAN 主机同时上传 60 秒。验证：两者的平均速率之差不超过 20%。
- [ ] 7.8 dae 行为：直连目标、代理目标、路由器本机访问、IPv6 代理目标、停止 dae 这五种情况。验证：每种情况的结果都符合 transparent-proxy 规格；启动 dae 时 dmesg 里没有 conntrack 告警（对应 issue #848）。
- [ ] 7.9 吞吐：直连 NAT 用 iperf3 测单流和多流；代理流量分别在绑定大核和不绑定两种情况下测试。验证：数据记录下来，并据此确定 design D5 里 CPU 绑定的默认值。
- [ ] 7.10 顺序稳定性：依次重启 qosify、einat、dae，然后重拨一次。验证：每一步之后程序的列表和顺序都满足 tc-hook-order 规格。
