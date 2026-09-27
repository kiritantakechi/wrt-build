# Tasks

## 1. 数据盘

- [ ] 1.1 新增 `config/services.seed`，内容见 design D9。验证：`just config ci` 的逐行校验通过。
- [ ] 1.2 在自有 feed 里实现 `wrt-data init`：列出候选磁盘，要求输入完整的设备名确认；然后建 btrfs、建子卷、写 UCI fstab。验证：在一块空白 SSD 上执行后，`btrfs subvolume list` 显示四个子卷加 `.snapshots`；重启后 `findmnt` 显示各子卷都挂在固定挂载点上，挂载选项包含 `compress=zstd:3,noatime`；不输入确认时什么都不改。
- [ ] 1.3 UUID 识别测试。验证：换一个 USB 口后仍然挂载到原处；插入另一块 btrfs 盘时，它没有被挂载到数据盘的挂载点上。
- [ ] 1.4 设置持久日志：`log_file=/mnt/data/logs/messages`，`log_size=64M`。验证：重启后之前的日志还在 `@logs` 里；不接数据盘时，SD 卡上没有出现这个日志文件。
- [ ] 1.5 在自有 feed 里实现 `wrt-snap` 的 `now` 和 `prune`，外加每天执行一次的 cron。验证：手动执行 `now` 后出现带时间戳的只读快照；伪造 9 天的快照目录后执行 `prune`，只剩最近 7 份。

## 2. 依赖挂载的启动顺序与降级

- [ ] 2.1 给 podman、`wrt-containers`、ksmbd 的 init 脚本加上 `procd_add_restart_mount_trigger`，并在挂载点不在时直接返回。验证：让数据盘延迟 30 秒挂载，服务在挂载完成后才启动；SD 卡上对应的同名目录里没有新写入的文件。
- [ ] 2.2 降级测试。验证：不接数据盘启动时，LAN 能上网、代理和 VPN 正常、健康检查通过，容器和 SMB 都没有运行。

## 3. 容器

- [ ] 3.1 修改 `containers.conf`，设置 `firewall_driver = "none"`；修改 `storage.conf`，把 graphroot 放到数据盘。验证：运行一个桥接网络的容器后，`nft list ruleset` 里没有 netavark 的表；拉一个镜像之后，`/overlay` 的使用量不变，`/mnt/data/containers/storage` 的使用量增加。
- [ ] 3.2 用 uci-defaults 加入 fw4 的 `podman` 区域和转发规则，并核对 einat 的内网网段设置包含容器网段。验证：容器访问外网时，外部看到的源地址是 WAN 地址，而且端口经过了 einat 映射（NAT 类型检测结果为完全锥形）；LAN 能访问容器的地址；容器访问不了 LAN。
- [ ] 3.3 写一个 fw4 redirect 的示例（容器端口开放到 WAN，端口不在 20000-29999 之内）。验证：从外部可以访问到这个容器端口。
- [ ] 3.4 在自有 feed 里实现 `wrt-containers`：遍历 `pods/*.yaml`，比较哈希后执行 `podman kube play --replace`，挂着数据盘的挂载触发器。附带一组 shell 测试，用模拟的 podman 命令覆盖“哈希变了”和“哈希没变”两种情况。验证：测试通过；上机放一个 qBittorrent 的 Pod YAML 后重启，容器自动运行；再触发一次时，容器 ID 不变。
- [ ] 3.5 验证容器流量走代理。验证：podman0 出现后，dae 在它上面挂了程序；容器访问代理目标时，经代理节点出口。

## 4. 文件共享

- [ ] 4.1 用 uci-defaults 配置 ksmbd：只绑定 lan，最低协议 SMB3，不允许访客，共享放在 `/mnt/data/shares`。fw4 只在 lan 上放行 445。验证：从 LAN 能看到共享列表；从 WAN、WireGuard 设备、tailnet 设备连接 445 都被拒绝；匿名访问被拒绝；强制使用 SMB1 的客户端协商失败。
- [ ] 4.2 在 macOS Finder 和一台 Linux 客户端上测试读写。验证：两者都能读写，大文件拷贝的速率记录在 `docs/validation/services.md`。

## 5. VPN

- [ ] 5.1 配置 WireGuard：wg0 放进 `wg` 区域，没有预置任何密钥。验证：用一台测试设备接入后能访问 LAN 主机；它访问外网时源地址是 WAN 地址；它访问不到路由器的 445 端口。
- [ ] 5.2 配置 Tailscale：使用 nftables 模式，宣告 LAN 子网路由。核对 tailscale 源码里用到的 mark，登记进 `config/marks.tsv`。验证：tailnet 设备能经子网路由访问 LAN 主机；把路由器设为出口节点后访问代理目标，走代理节点出口；`just lint` 的 mark 检查通过。

## 6. 监控

- [ ] 6.1 配置 node-exporter：`listen_interface 'lan'`，打开 cpu、meminfo、netdev、filesystem、hwmon 采集器。验证：从 LAN 执行 `curl http://10.0.0.1:9101/metrics`，能看到这五类指标；从 WAN 访问被拒绝；不接数据盘时仍能返回指标。

## 7. 硬件与文档

- [ ] 7.1 硬件实测：用选定的 SSD 和硬盘盒，在 UAS 模式下持续读写 1 小时，同时满速下载。验证：dmesg 里没有 USB 复位或 UAS 错误；结果记录在 `docs/validation/services.md`；如果有问题，记录下 quirks 的处理办法。
- [ ] 7.2 编写 `docs/services.md`：数据盘初始化、Pod 声明文件的写法、怎样用 fw4 开放端口、快照恢复的步骤。验证：按文档从一次快照里恢复出一个被删掉的共享文件，能恢复成功。
