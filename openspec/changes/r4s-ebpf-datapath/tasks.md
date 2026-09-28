# Tasks

## 1. 打包

- [ ] 1.1 在自有 feed 里新增 dae 2.1.1：以 ImmortalWrt 的 Makefile 为起点，BPF 用宿主 clang 编译，Go 模块按 `go.sum` 校验。验证：CI 构建成功；模拟器用例确认 `dae --version` 输出 2.1.1。
- [ ] 1.2 审查 `olicesx/outbound` 在 `go.sum` 固定的那个版本与上游 `daeuniverse/outbound` 之间的差异，把结论写进 `docs/supply-chain/dae.md`。验证：文档里有差异摘要和是否接受的结论；如果结论是不接受，要先解决再继续后面的任务。
- [ ] 1.3 新增 luci-app-dae。验证：由 `test_transparent_proxy.py` 中“在 LuCI 里保存配置”的用例覆盖。
- [ ] 1.4 在自有 feed 里新增 einat：只用 aya 加载器，不启用 ipv6 特性，Rust 依赖按 `Cargo.lock` 校验。验证：模拟器用例确认 `einat --version` 输出 0.1.11；镜像审计确认可执行文件不依赖 libbpf 和 libelf（`readelf -d`）。
- [ ] 1.5 编写 einat 的 mark 补丁（design D2），并在 `docs/upstream/` 准备好提交材料，但不提交。验证：`test_nat.py` 的放行用例确认按 mark 放行的规则计数在增长；不设置 `--inbound-mark` 时，另一条用例确认报文没有被打标。
- [ ] 1.6 新增 `config/datapath.seed`：kmod-sched-core、kmod-sched-bpf、kmod-veth、kmod-sched-cake、qosify、dae、luci-app-dae、einat、bpftool-minimal。验证：`just config ci` 的逐行校验通过。

## 2. mark 分配表

- [ ] 2.1 建立 `config/marks.tsv`，初始内容见 design D4。验证：`editorconfig-checker` 通过；每一行都有四列，并且掩码是合法的十六进制数。
- [ ] 2.2 实现 `scripts/marks-check.sh`，接进 `just check`。验证：`tests/network/test_tc_hook_order.py` 中“配置了重叠的 mark”的用例（只在宿主上运行）在夹具模板里写一个与 dae 重叠的 mark，检查失败并报出冲突的两方；删掉之后检查通过。

## 3. 模拟的运营商与互联网（design D11）

- [ ] 3.1 把 rp-pppoe、ppp、kea、radvd、dnsmasq、microsocks、iperf3、iputils 加进 flake 的测试工具组；`prepare-runner.sh` 和 `docs/dev-setup.md` 负责加载 `ppp_generic`、`ppp_async`，并放开 `/dev/ppp` 的权限；`env-report` 检查这两项。验证：`just env-report` 输出工具版本和 ppp 检查结果；缺少 ppp 支持时，它报错并给出修复方法。
- [ ] 3.2 在 `wrt_tests/net.py` 的拓扑声明里增加 `client-b`、`inet`、`proxy` 三个命名空间和 `br-inet` 网桥。验证：`tests/unit/test_net.py` 在不启动模拟器的情况下建起拓扑，确认各命名空间的地址和路由与 design D11 一致。
- [ ] 3.3 实现 `isp` 一侧：用户态 pppoe-server，每个会话启动 radvd 和 kea-dhcp6，地址池每次重拨换一个地址。验证：`tests/unit/test_isp.py` 用沙箱里的 pppd 作为客户端拨号，拿到池内地址和 /56 前缀；结束会话后重拨，拿到的是另一个地址。
- [ ] 3.4 实现 `wrt_tests/netprobe.py`：UDP/TCP whoami（返回对端地址、端口和 MSS）、“big”模式（返回 3000 字节的 UDP 回应），以及 ESP 原始报文的收发。`inet` 里再跑 example.test 的权威 dnsmasq 和 iperf3，`proxy` 里跑 microsocks。验证：`tests/unit/test_netprobe.py` 在两个普通命名空间之间覆盖 netprobe 的每种模式。

## 4. WAN、防火墙与 einat 集成

- [ ] 4.1 用 uci-defaults 生成 WAN 和 LAN 的配置：PPPoE 不含凭据、`ipv6 auto`、`mtu_fix 1`、`flow_offloading 1`、`ip6assign 64`，只在选项尚未设置时写入。验证：由 `test_wan.py` 覆盖；另有一条用例在修改配置后做一次保留配置升级，确认修改的值没有被覆盖。
- [ ] 4.2 编写 einat 的 init 脚本：通过 procd 注入 design D3 里的两条防火墙规则，传入 `--inbound-mark` 和端口范围。验证：由 `test_nat.py` 覆盖；其中“停止 einat”的用例确认这两条规则随之消失。
- [ ] 4.3 注册 `/etc/healthcheck.d/50-einat`。验证：`test_nat.py` 的健康检查用例覆盖三种情况：einat 没运行时判失败；einat 在运行但 pppoe-wan 不存在时判通过；pppoe-wan 存在但没挂上 einat 时判失败。

## 5. dae 集成

- [ ] 5.1 实现 design D5 的配置结构：镜像里的 `config.dae` 只负责 include；init 脚本生成 `generated/10-bind.dae`；`user/` 目录留空并提供示例。验证：`test_transparent_proxy.py` 用测试配置（socks5 节点指向 `proxy`）覆盖分流用例；include 的合并语义以用例结果为准，结论写进 design 的风险说明。
- [ ] 5.2 实现 hotplug：podman0 或 tailscale0 出现或消失时，重新生成绑定片段并执行 `dae reload`。验证：由“容器网桥比 dae 晚出现”的用例覆盖（在模拟器里用 `ip link add podman0 type bridge` 代替真实容器），另有一条用例确认接口删除后 dae 仍在运行。
- [ ] 5.3 在 init 脚本里加入可选的 CPU 绑定参数，默认关闭。验证：模拟器有 6 个 vCPU，用例打开这个参数后，`taskset -p $(pidof dae)` 显示 cpu4-5。
- [ ] 5.4 注册 `/etc/healthcheck.d/50-dae`。验证：`test_transparent_proxy.py` 的健康检查用例覆盖三种情况：dae 没运行时判失败，程序缺失时判失败，正常时判通过。

## 6. DNS

- [ ] 6.1 配置 dnsmasq：`server=127.0.0.1#5353` 排在前面，打开 `strictorder`，保留 WAN 上获得的上游；dae 的 `dns.bind` 设为 127.0.0.1:5353。验证：由 `test_dns.py` 覆盖 dns 规格的全部场景。

## 7. QoS

- [ ] 7.1 配置 qosify：只开出方向，设置上行带宽和封装开销，模式为 diffserv4 加 nat 和 host_isolate，另加游戏和视频会议的端口规则。验证：由 `test_qos.py` 覆盖 qos 规格的全部场景。

## 8. 模拟器用例（全部在 `just test` 中运行）

- [ ] 8.1 `tests/network/test_tc_hook_order.py`：两个网口上的程序列表和顺序；ICMP 回应和分片 UDP 回应能完整送达，并且 qosify 的入方向统计增加；依次重启 qosify、einat、dae 再重拨，每一步之后顺序都不变；mark 冲突用例见 2.2。验证：用例全部通过。
- [ ] 8.2 `tests/network/test_nat.py`：映射与外部端点无关、过滤与外部端点无关；两条伪造入站路径（PPP 会话内和 eth0 二层）都被丢弃；已映射端口的入站被放行；ESP 双向通过并以 WAN 地址发出；停止 einat 后回落；本机连接不被改写；IPv6 不转换；重拨后 60 秒内恢复；健康检查。验证：用例全部通过。
- [ ] 8.3 `tests/network/test_transparent_proxy.py`：两个网口上的程序；容器网桥比 dae 晚出现；直连目标（`netprobe` 看到 WAN 地址，路由器上没有 dae 到该目标的连接）；代理目标和 IPv6 代理目标（看到 `proxy` 的地址）；路由器本机访问直连；通过 LuCI 的 HTTP 接口保存配置触发热重载，期间直连不中断；镜像里只有模板；停止 dae 后回落到直连；健康检查；dmesg 里没有 conntrack 告警。验证：用例全部通过。
- [ ] 8.4 `tests/network/test_dns.py`：`.lan` 主机名由 dnsmasq 直接回答；外部域名经 dae 解析并出现在 dae 日志里；停止 dae 后回落到上游；从 LAN 访问 5353 端口得不到响应。验证：用例全部通过。
- [ ] 8.5 `tests/network/test_qos.py`：cake 按配置带宽运行，唯一的 ifb 是 `ifb-dns`；上行带宽设为 20 Mbit/s 时，`client-a` 和 `client-b` 同时上传 60 秒，平均速率之差不超过 20%；命中 voice 规则的流量进入语音档位；重拨后 60 秒内恢复。验证：用例全部通过。
- [ ] 8.6 `tests/network/test_wan.py`：镜像里的凭据为空；推送凭据后拨号成功；MSS 不超过 1452，PMTU 为 1492；LAN 主机拿到 PD 前缀内的地址并能访问 IPv6 外网；外部主动连接内网 IPv6 地址被拒绝；持续下载时连接带有 `[OFFLOAD]` 标记，`netprobe` 看到的源地址始终是 WAN 地址，并记录入方向是否命中 flowtable。验证：用例全部通过；`spec-coverage` 显示这个 change 除了仅真机的场景外，没有未覆盖的场景。

## 9. 真机冒烟

- [ ] 9.1 编写 `@target("device")` 用例：直连 NAT 单流和多流的吞吐；代理流量在绑定 A72 与不绑定两种情况下的吞吐；真实线路上拨号成功、拿到 PD 前缀，外部 STUN 显示完全锥形。验证：在模拟器上运行时这些用例被跳过并显示原因。
- [ ] 9.2 运行 `just test-device <host>`，结果存档到 `docs/validation/datapath-device.md`，并据此确定 design D5 里 CPU 绑定的默认值。验证：报告全部通过，默认值已经写回 init 脚本和 design。
