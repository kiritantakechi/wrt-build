# Design

## Context

动机见 proposal.md。以下现状都在上游源码里核对过（OpenWrt main `1019293`，packages `a637759`）：

- **podman**：
  - 版本 5.8.4。`containers.conf` 默认 `network_backend = "netavark"`、`firewall_driver = "nftables"`、`cgroup_manager = "cgroupfs"`。
  - `storage.conf` 的驱动被 sed 改成了 `overlay`（`utils/podman/Makefile:113`）。
  - `podman.init` 只负责运行 `podman system service`，不会在开机时拉起容器。
- **netavark**：版本 1.17.2，默认防火墙后端是 nftables，依赖 `kmod-nft-nat`。
- **持久日志**：上游 `log.init` 已经支持把 `log_file` 放在挂载点上。开机时挂载点还没挂好就先跳过，并用 `-S` 按大小轮转（`package/system/ubox/files/log.init:53-66`）。
- **node-exporter**：`prometheus-node-exporter-ucode` 默认 `listen_interface 'loopback'`，端口 9101。
- **tailscale**：init 默认 `fw_mode nftables`（`net/tailscale/files/tailscale.init:22-31`）。
- **ksmbd**：ksmbd-tools 3.5.7，内核模块是 `kmod-fs-ksmbd`（`package/kernel/linux/modules/fs.mk:346`），luci 里有对应的 luci-app-ksmbd。
- **procd**：提供 `procd_add_restart_mount_trigger`（`procd.sh:431`）。
- **上游 change**：数据面的 einat、fw4 规则和 dae 绑定来自 `r4s-ebpf-datapath`；mark 分配表也在那里建立。
- **内核**：rockchip 的配置没有开 `USB_PCI` 和 `USB_XHCI_PCI`（在 6.18.52 的构建结果里核对过），模拟器里的 USB 控制器需要这两项。
- **验证环境**：foundation 的模拟环境和 datapath 补齐的运营商、互联网与代理节点（datapath D11）。

## Goals / Non-Goals

**Goals:**
- SD 卡上只有系统和少量配置写入，所有写入较重的负载都在 USB SSD 上。
- 防火墙和 NAT 各只有一个来源：防火墙都由 fw4 管，NAT 都由 einat 做（einat 不可用时回落到 masquerade）。容器运行时不自己装规则。
- 应用容器以声明文件定义，可以重复执行、结果一致。

**Non-Goals:**
- 从 VPN 访问 SMB 或其他路由器本机服务。
- 在固件里原生打包 qBittorrent、AdGuardHome 等应用。
- 数据盘做 RAID 或多盘阵列，也不做异地备份。
- Time Machine（已经决定用 ksmbd，而不用 samba4）。

## Decisions

### D1. 挂载布局

```
USB SSD  (btrfs, label wrtdata, identified by UUID)
  subvolid=5   -> /mnt/data/.pool        (management only; snapshots created here)
  @containers  -> /mnt/data/containers
  @downloads   -> /mnt/data/downloads
  @shares      -> /mnt/data/shares
  @logs        -> /mnt/data/logs
  .snapshots   (under the pool root)
options: compress=zstd:3,noatime,space_cache=v2
```

- **挂载方式**：用 fstools 的 block-mount，在 UCI fstab 里为每个子卷写一条 mount，UUID 相同，但 `subvol=` 不同。
- **初始化**：`wrt-data init` 负责建子卷、写 fstab。执行之前必须人工确认目标磁盘，因为它会清空整个盘。
- **备选方案**：
  - 整盘只挂一个点，再用子目录区分。否决，因为那样没法对单个子卷做快照，也没法用挂载触发器单独等待某个子卷。
  - ext4 或 xfs。探索阶段已经决定用 btrfs。

### D2. 依赖挂载的启动顺序

- **做法**：所有依赖数据盘的服务都在 init 脚本里声明 `procd_add_restart_mount_trigger <对应挂载点>`，启动时如果挂载点不在就直接返回，不建目录。这些服务包括 podman、`wrt-containers`、ksmbd 和持久日志。
- **为什么启动时不建目录**：这样可以避免数据盘不在时，把目录建到 SD 卡上，满足规格里“不能把数据写到 SD 卡”那一条。
- **持久日志的具体做法**：直接用上游机制，设置 `system.@system[0].log_file=/mnt/data/logs/messages` 和 `log_size`，不需要自己写服务。

### D3. 容器：netavark 不管防火墙，fw4 统一管理

- **podman 配置**：
  - `containers.conf` 里改为 `firewall_driver = "none"`，netavark 只负责建网桥和分配地址，不装任何 nft 规则。
  - `storage.conf` 里 `graphroot=/mnt/data/containers/storage`，`runroot=/run/containers/storage`。
- **fw4 配置**：新增一个 `podman` 区域，包含 podman0：
  - podman → wan 允许转发；
  - lan → podman 允许转发，这样 LAN 可以直接访问容器的地址；
  - podman → lan 默认拒绝。
- **出网的地址转换**：和 LAN 一样由 einat 完成，einat 不可用时回落到 masquerade。实施时要确认 einat 的内网网段设置包含容器网段（任务 4.2）。
- **对外开放端口**：用 fw4 的 redirect（DNAT）实现，外部端口不能落在 einat 的端口范围 20000-29999 里。
- **理由**：
  - 规则只有 fw4 一个来源，`nft list ruleset` 一眼就能看全；
  - 避免 netavark 的 masquerade 和 einat 叠加，导致外部端口被改写两次；
  - netavark 不用 mark，也就少了一个要登记进分配表的组件。
- **代价**：`podman run -p` 不能再用，要开放端口必须写 fw4 规则。
- **备选方案**：保留 netavark 的 nftables 后端。否决，理由就是上面几条。

### D4. 应用容器用声明文件定义

- **声明文件**：用 `podman kube play` 读取的 Kubernetes Pod YAML，放在 `/mnt/data/containers/pods/*.yaml`。正本放在私有配置仓库，由推送工具写入。
- **启动服务**：自有 feed 新增 `wrt-containers` 服务，挂着 `/mnt/data/containers` 的挂载触发器。每次触发时，逐个比较声明文件的哈希和上次成功应用时记录的哈希：
  - 哈希变了，就执行 `podman kube play --replace`；
  - 哈希没变，就只确保 Pod 在运行。
  - 这样满足“声明未变就不重建”。
- **备选方案**：
  - podman-compose。上游 feed 里没有，还要引入 Python。否决。
  - 每个容器写一个 procd 服务。否决，太分散。

### D5. 快照

- **工具**：自有 feed 新增 `wrt-snap`：
  - `wrt-snap now` 对 `@containers` 和 `@shares` 各做一份只读快照，放到 `.snapshots/<子卷名>/<时间戳>`；
  - `wrt-snap prune` 只保留最近 7 天；
  - cron 每天执行一次 `now` 和 `prune`。
- **为什么不包括 `@downloads` 和 `@logs`**：下载内容可以重新获取，日志本身就会轮转，给它们做快照只会占空间。

### D6. ksmbd

- **协议和认证**：用 UCI 配置 ksmbd 只绑定 `lan`，协议下限为 SMB3，不允许匿名访问。
- **共享目录**：共享都指向 `/mnt/data/shares/*`。
- **凭据**：用户凭据由推送工具在设备上执行 `ksmbd.adduser` 写入，不预置在镜像里。
- **防火墙**：fw4 的 wan、wireguard、tailscale 区域的 input 默认拒绝，445 端口只对 lan 放行。

### D7. VPN

- **WireGuard**：
  - 用 `kmod-wireguard`、`wireguard-tools` 和 `luci-proto-wireguard`；接口 wg0 单独放在 `wg` 区域，允许转发到 lan 和 wan。
  - wg0 不加入 dae 的绑定列表，所以经 WireGuard 进来的流量直连。
- **Tailscale**：
  - 使用上游包，`fw_mode nftables`，宣告 LAN 子网路由，也可以作为出口节点。
  - tailscale0 由 datapath 的 hotplug 自动加入 dae 的绑定。
  - 它使用的 mark（掩码 `0xff0000` 里的 `0x40000` 和 `0x80000`）要在实施时核对 tailscale 源码后确认，再登记进 `config/marks.tsv`。
- **凭据**：WireGuard 的私钥和 Tailscale 的认证密钥都由推送工具写入。

### D8. 监控

- **配置**：`prometheus-node-exporter-ucode` 的 `listen_interface 'lan'`，只对 lan 区域开放 9101 端口。
- **采集器**：包括 cpu、meminfo、netdev、filesystem、hwmon（温度）。

### D9. 新增的软件包和内核模块

```
kmod-usb-storage kmod-usb-storage-uas kmod-fs-btrfs btrfs-progs block-mount
podman crun netavark conmon
kmod-fs-ksmbd ksmbd-tools luci-app-ksmbd
kmod-wireguard wireguard-tools luci-proto-wireguard tailscale
prometheus-node-exporter-ucode (+ collectors)
wrt-containers wrt-snap wrt-data   (own feed)
```

这些都放进 `config/services.seed`。

### D10. 验证方式：USB 数据盘和各类对端都在模拟器里

```
qemu ... -device qemu-xhci,id=xhci
  data disk : -drive if=none,id=ssd,file=ssd.qcow2 -device usb-uas,id=uas,bus=xhci.0,port=1
              -device scsi-hd,bus=uas.0,drive=ssd
  QMP       : device_add / device_del  -> late attach, other port (port=2), foreign btrfs disk
sandbox additions:
  inet     : registry (distribution, TLS by test CA)   headscale (+ embedded DERP, same CA)
  wg-peer  : wireguard-go + wireguard-tools             remote WireGuard device
  ts-peer  : tailscaled --tun, logged into headscale    tailnet device
  client-a : smbclient, curl
test image: busybox + musl taken from the shipped rootfs -> OCI image -> skopeo push
```

- **内核补充**：`config/kernel.config` 的 virt 驱动组加上 `USB_PCI` 和 `USB_XHCI_PCI`。UAS 驱动来自镜像里的 `kmod-usb-storage-uas`，模拟器用 `usb-uas` 设备，走的是和真机一样的驱动。
- **插拔**：通过 QMP 的 `device_add` 和 `device_del` 完成，所以“晚 30 秒挂载”“换一个 USB 口”“插入另一块盘”“拔盘降级”都能自动执行。
- **测试用容器镜像**：直接用出货 rootfs 里的 busybox 和 musl 拼成一个 OCI 镜像，架构一定对得上，也不用访问外网。用例里的应用容器是一个 busybox httpd，代替 qBittorrent 的角色。
- **测试 CA**：registry 和 headscale 共用一个测试 CA。夹具把 CA 证书写进路由器的 `/etc/ssl/certs/`，它只存在于测试用的 overlay 里，不会进入镜像。
- **凭据**：SMB 用户、WireGuard 密钥、Tailscale 认证密钥都由夹具按推送工具的方式写入，同时验证“镜像里没有预置凭据”。
- **用例与规格一一对应**：`tests/storage/test_data_disk.py`，以及 `tests/services/` 下的 `test_containers`、`test_file_sharing`、`test_vpn`、`test_monitoring`。
- **快照过期**：用例把系统时间逐日往前拨，在每一天执行一次 cron 任务，不需要等待真实时间。
- **只能留给真机的**（写成 `@target("device")` 用例）：
  1. 温度指标（模拟器没有温度传感器）；
  2. 选定的 SSD 和硬盘盒在 UAS 模式下满负载 1 小时的稳定性；
  3. macOS Finder 读写共享和大文件拷贝速率（用例提示人工操作并记录结果）。

## Risks / Trade-offs

- **[USB3 供电不足，或者桥接芯片在 UAS 模式下不稳定]** → 优先选低功耗的 SATA SSD 和 ASM1153、JMS578 这类稳定的桥接芯片。出现问题就把这个设备加进 `usb-storage` 的 quirks，退回 BOT 模式。真机用例记录实测结果。
- **[模拟器只覆盖驱动之上的行为]** 桥接芯片、供电和 USB 链路重置这些问题在模拟器里不会出现。→ 由真机的满负载用例覆盖。
- **[`firewall_driver = "none"` 以后 `podman run -p` 失效]** 这是有意的取舍；开放端口统一用 fw4 的 redirect，写进文档。
- **[einat 的内网网段设置没有包含容器网段]** → `test_containers.py` 用 `netprobe` 检查容器流量的映射行为。
- **[btrfs 在异常断电后出问题]** btrfs 是写时复制，一般能保持一致；定期的只读快照可以作为恢复点。
- **[ksmbd 的漏洞历史]** → 只在 LAN 开放；跟随每周 bump 更新内核。
- **[容器镜像要从外网拉取]** 容器网段已经纳入 dae，拉镜像可以按规则走代理。

## Migration Plan

1. 部署含本 change 的固件。
2. 接上新的 SSD，执行 `wrt-data init` 并按提示确认目标磁盘。
3. 用推送工具写入 SMB 用户、WireGuard 私钥、Tailscale 认证密钥和 Pod 声明文件。
4. 回退：拔掉数据盘，系统会降级为纯路由；需要回退固件时，用 A/B 切回上一个槽位。

## Open Questions

- 具体用哪款 SSD 和硬件盒，要等实测后再定，不影响规格。
- 日志轮转的大小上限先定为 64 MiB，可以随时调整。
