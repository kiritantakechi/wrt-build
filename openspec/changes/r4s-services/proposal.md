# Proposal

## Why

R4S 除了路由，还要做 NAS、下载、容器和远程组网。SD 卡是唯一的启动介质，写得多的负载必须挪出 SD 卡。

qBittorrent 这类应用需要 Qt6 和 libtorrent，如果原生打包，自有 feed 会大幅膨胀。所以这类应用放进容器，固件里只保留核心组件。

## What Changes

- **USB SSD 数据盘**
  - 文件系统用 btrfs，挂载参数 `compress=zstd:3,noatime`。
  - 子卷划分：`@containers`、`@downloads`、`@shares`、`@logs`，以及 `.snapshots`。
  - 由 fstools 的 block-mount 按 UUID 挂载。
- **服务等盘再启动**：依赖数据盘的服务用 procd 的挂载点触发器（`procd_add_restart_mount_trigger`）在盘挂好之后启动或重启，不用 sleep 轮询。
- **容器**
  - 用 podman + crun + netavark；容器存储（graphroot）放在 `@containers`。
  - netavark 只负责建网桥和分配地址，不安装任何防火墙规则（`firewall_driver = "none"`）。容器网桥归入 fw4 的一个独立区域，出网的地址转换和 LAN 一样由 einat 完成；需要对外开放端口时，用 fw4 的端口转发。
  - 容器网桥 podman0 纳入 dae 的 LAN 绑定。
  - qBittorrent 等应用都以容器方式运行。
- **文件共享**
  - 用 ksmbd（内核里的 SMB 服务）加 ksmbd-tools。
  - 只在 LAN 开放，共享目录放在 `@shares`。
- **组网**
  - WireGuard（内核自带）和 Tailscale。
  - tailscale0 纳入 dae 的 LAN 绑定。
- **监控**：prometheus-node-exporter-ucode，只在 LAN 暴露。
- **日志**：持久日志写到 `@logs`，SD 卡上基本没有写入。
- **数据盘缺失时降级**：容器和 SMB 不启动，路由核心功能不受影响。

## Capabilities

### New Capabilities

- `storage/data-disk`：USB SSD 的文件系统、子卷布局、挂载方式、依赖挂载的服务启动顺序、持久日志，以及数据盘缺失时的降级行为。
- `services/containers`：podman 运行时、存储位置、容器网络和代理的关系，以及以容器运行应用的边界。
- `services/file-sharing`：ksmbd 共享的暴露范围和共享目录。
- `services/vpn`：WireGuard 与 Tailscale，以及它们和透明代理的关系。
- `services/monitoring`：指标导出和暴露范围。

### Modified Capabilities

（无。）

## Impact

- **kmod**：kmod-fs-btrfs、kmod-usb-storage-uas、kmod-fs-ksmbd、kmod-wireguard、kmod-tun（Tailscale 用）、kmod-veth。
- **软件包**：btrfs-progs、block-mount、podman、crun、netavark、ksmbd-tools、tailscale、prometheus-node-exporter-ucode。
- **依赖其他 change**：
  - `r4s-build-foundation`：cgroup v2 和内核特性。
  - `r4s-ebpf-datapath`：podman0 和 tailscale0 绑定到 dae。
- **内核**：`config/kernel.config` 的 virt 驱动组加上 `USB_PCI` 和 `USB_XHCI_PCI`，让模拟器能挂 USB 数据盘。
- **验证方式**：模拟器里用 `usb-uas` 设备充当 SSD，插拔通过 QEMU 的控制接口完成；沙箱里加上镜像仓库、headscale、WireGuard 对端和 tailnet 对端。五个规格除温度以外的场景都写成 `just test` 里的自动用例。
- **硬件风险**：R4S 的 USB3 口供电有限；部分 USB 转 SATA/NVMe 的桥接芯片在 UAS 模式下不稳定。需要选型，并用真机用例做满负载实测。
- **安全**：ksmbd 历史上出过严重漏洞。要依赖每周跟进内核修复，并且只在 LAN 暴露。
