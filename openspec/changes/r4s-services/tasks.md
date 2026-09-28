# Tasks

## 1. 内核与模拟环境（design D10）

- [ ] 1.1 在 `config/kernel.config` 的 virt 驱动组里加入 `CONFIG_USB_PCI=y` 和 `CONFIG_USB_XHCI_PCI=y`，并用 `listnewconfig` 补全子选项。验证：构建后的内核配置校验通过；模拟器里 `lsusb -t` 能看到 xHCI 根集线器。
- [ ] 1.2 扩展模拟器夹具：挂上 `qemu-xhci`；数据盘用 `usb-uas` 加 `scsi-hd`；通过 QMP 的 `device_add` 和 `device_del` 在指定端口插拔磁盘。验证：`tests/testing/test_emulation.py` 里新增的自检用例确认热插入的磁盘在 dmesg 里走的是 uas 驱动，拔出后设备消失。
- [ ] 1.3 在 `wrt_tests/` 里实现测试 CA，以及由出货 rootfs 中 busybox 和 musl 拼成 OCI 镜像的工具；`inet` 里跑 distribution 镜像仓库和 headscale（内置 DERP）；新增 `wg-peer` 和 `ts-peer` 两个命名空间。相关工具（distribution、skopeo、samba 的 smbclient、wireguard-go、wireguard-tools、headscale、tailscale、curl）加进 flake 的测试工具组。验证：`tests/unit/test_oci.py` 在宿主上用 skopeo 检查生成的镜像，架构是 arm64；`tests/unit/test_net.py` 确认新命名空间的地址和路由正确。

## 2. 数据盘

- [ ] 2.1 新增 `config/services.seed`，内容见 design D9。验证：`just config ci` 的逐行校验通过。
- [ ] 2.2 在自有 feed 里实现 `wrt-data init`：列出候选磁盘，要求输入完整的设备名确认；然后建 btrfs、建子卷、写 UCI fstab。验证：`test_data_disk.py` 在空白磁盘上执行初始化并重启，覆盖“检查挂载”场景；另有一条用例确认不输入确认时磁盘没有任何改动。
- [ ] 2.3 设置持久日志：`log_file=/mnt/data/logs/messages`，`log_size=64M`。验证：由“重启后查看日志”的用例覆盖；另有一条用例确认不接数据盘时 SD 卡上没有出现这个日志文件。
- [ ] 2.4 在自有 feed 里实现 `wrt-snap` 的 `now` 和 `prune`，外加每天执行一次的 cron。验证：由两个快照场景的用例覆盖（过期清理靠逐日调整系统时间）。

## 3. 依赖挂载的启动顺序与降级

- [ ] 3.1 给 podman、`wrt-containers`、ksmbd 的 init 脚本加上 `procd_add_restart_mount_trigger`，并在挂载点不在时直接返回。验证：由“数据盘挂载得比较晚”的用例覆盖（开机 30 秒后通过 QMP 插入磁盘）。
- [ ] 3.2 降级行为。验证：由“不接数据盘启动”的用例覆盖，其中复用 datapath 的探测确认 LAN 能上网、代理正常，并确认 A/B 健康检查通过。

## 4. 容器

- [ ] 4.1 修改 `containers.conf`，设置 `firewall_driver = "none"`；修改 `storage.conf`，把 graphroot 放到数据盘。验证：由“拉取一个镜像”和“检查规则集”两个用例覆盖。
- [ ] 4.2 用 uci-defaults 加入 fw4 的 `podman` 区域和转发规则，并核对 einat 的内网网段设置包含容器网段。验证：由“容器访问外网”的用例覆盖，其中容器用 busybox `nc` 从同一个源端口先后访问两个探测地址，看到的公网端口相同（证明经过了 einat）；另有两条用例确认 LAN 能访问容器、容器访问不了 LAN。
- [ ] 4.3 写一个 fw4 redirect 的示例（容器端口开放到 WAN，端口不在 20000-29999 之内）。验证：由“对外开放容器端口”的用例覆盖，从 `inet` 访问。
- [ ] 4.4 在自有 feed 里实现 `wrt-containers`：遍历 `pods/*.yaml`，比较哈希后执行 `podman kube play --replace`，挂着数据盘的挂载触发器。验证：由“开机自动启动”和“声明未改变”两个用例覆盖（后者比较容器 ID）。
- [ ] 4.5 容器流量走代理。验证：由“容器访问代理目标”的用例覆盖；用例同时确认 podman0 出现后 dae 在它上面挂了程序。

## 5. 文件共享

- [ ] 5.1 用 uci-defaults 配置 ksmbd：只绑定 lan，最低协议 SMB3，不允许访客，共享放在 `/mnt/data/shares`；fw4 只在 lan 上放行 445。验证：由 file-sharing 规格的全部用例覆盖，用 smbclient 从 `client-a`、`inet`、`wg-peer`、`ts-peer` 分别连接，SMB1 用 `client max protocol = NT1` 强制协商。

## 6. VPN

- [ ] 6.1 配置 WireGuard：wg0 放进 `wg` 区域，没有预置任何密钥。验证：由“远程设备接入”和“WireGuard 设备访问外网”两个用例覆盖，对端是 `wg-peer`。
- [ ] 6.2 配置 Tailscale：使用 nftables 模式，宣告 LAN 子网路由；核对 tailscale 源码里用到的 mark，登记进 `config/marks.tsv`。验证：由“通过子网路由访问 LAN”“tailnet 设备访问代理目标”“检查分配表”三个用例覆盖，对端是登录到 headscale 的 `ts-peer`。

## 7. 监控

- [ ] 7.1 配置 node-exporter：`listen_interface 'lan'`，打开 cpu、meminfo、netdev、filesystem、hwmon 采集器。验证：由 monitoring 规格的用例覆盖；温度场景是仅真机用例。

## 8. 模拟器用例（全部在 `just test` 中运行）

- [ ] 8.1 `tests/storage/test_data_disk.py`：覆盖 data-disk 规格的全部场景。验证：用例全部通过。
- [ ] 8.2 `tests/services/test_containers.py`：覆盖 containers 规格的全部场景；“检查镜像”场景读取镜像审计输出的软件包列表。验证：用例全部通过。
- [ ] 8.3 `tests/services/test_file_sharing.py`、`test_vpn.py`、`test_monitoring.py`：覆盖对应规格的全部场景。验证：用例全部通过；`spec-coverage` 显示这个 change 除了仅真机的场景外，没有未覆盖的场景。

## 9. 真机冒烟与文档

- [ ] 9.1 编写 `@target("device")` 用例：温度指标；选定的 SSD 和硬盘盒在 UAS 模式下持续读写 1 小时，同时满速下载，dmesg 里没有 USB 复位或 UAS 错误；macOS Finder 读写共享（提示人工操作，记录大文件拷贝速率）。验证：在模拟器上运行时这些用例被跳过并显示原因。
- [ ] 9.2 运行 `just test-device <host>`，结果存档到 `docs/validation/services-device.md`；如果 UAS 不稳定，记录 quirks 的处理办法。验证：报告全部通过。
- [ ] 9.3 编写 `docs/services.md`：数据盘初始化、Pod 声明文件的写法、怎样用 fw4 开放端口、快照恢复的步骤。验证：`test_data_disk.py` 中“从快照恢复文件”的用例执行的正是文档里的命令，用例通过。
