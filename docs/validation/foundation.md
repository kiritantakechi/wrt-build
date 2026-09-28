# r4s-build-foundation 上机验证

所用镜像：`$WRT_WORKDIR/out/<profile>/targets/openwrt-*-friendlyarm_nanopi-r4s-erofs-sysupgrade.img.gz`。

## 准备工作

- 用 `gzip -dc <img.gz> | sudo dd of=/dev/<sd> bs=4M conv=fsync` 把镜像写入 microSD 卡，写之前务必确认设备名。
- 电脑直连 R4S 的 LAN 口（靠近 USB 口的那个），用 DHCP 获取地址。
- 所有命令都在 R4S 上执行（`ssh root@10.0.0.1`），除非另有说明。

## 核对清单

| # | 规格场景 | 命令或操作 | 期望结果 | 结果 |
|---|---|---|---|---|
| 1 | 只读根是 EROFS | `mount \| grep ' /rom '` | 类型是 `erofs` | |
| 2 | overlay 是 f2fs + zstd | `mount \| grep ' /overlay '` | 类型是 `f2fs`，选项里有 `compress_algorithm=zstd` | |
| 3 | LAN 地址 | `ip -4 addr show br-lan` | `10.0.0.1/24` | |
| 4 | 故障安全模式 | 开机时按 reset 键进入 failsafe，然后 `ping 10.0.0.1` | 可以访问 | |
| 5 | LuCI 简体中文 | 浏览器打开 `http://10.0.0.1` | uhttpd 提供页面，界面是中文 | |
| 6 | BTF | `ls -l /sys/kernel/btf/vmlinux` | 文件存在且非空 | |
| 7 | 只有 cgroup2 | `mount \| grep cgroup` | 只有 `cgroup2`，没有 v1 控制器 | |
| 8 | BBRv3 + fq | `sysctl net.ipv4.tcp_congestion_control net.core.default_qdisc; grep -E 'bbr_(skb_marked_lost\|tso_segs)' /proc/kallsyms` | 依次是 `bbr`、`fq`，并且能找到这两个符号（BBRv3 才有；OpenWrt 会去掉模块版本号，所以不看版本） | |
| 9 | 本机连接用 BBR | 执行 `wget -O /dev/null <大文件>` 时，另开一个终端运行 `ss -ti` | 这条连接显示 `bbr` | |
| 10 | zram | `swapon; cat /sys/block/zram0/comp_algorithm` | 有 1 GiB 的 zram，当前压缩算法是 `[zstd]` | |
| 11 | 恢复出厂只清空 overlay | 写一个文件到 `/etc/`，记下 `/rom` 的校验和，执行 `firstboot -y && reboot` | 文件消失，`/rom` 的校验和不变 | |
| 12 | SSH 交互登录进 zsh | `ssh root@10.0.0.1`，然后 `echo $ZSH_VERSION` | 有输出，两个插件都已加载 | |
| 13 | 非交互命令用 ash | 在电脑上运行 `ssh root@10.0.0.1 'echo $0; echo ${ZSH_VERSION:-none}'` | 输出 `ash`（或 `-ash`）和 `none` | |
| 14 | zsh 不可用时退回 ash | `mv /usr/bin/zsh /usr/bin/zsh.off` 之后重新登录，测完再改回来 | 能登录，停在 ash | |
| 15 | 不需要文件系统模块 | `lsmod \| grep -E 'erofs\|f2fs'` | 没有输出，说明两者都编进了内核 | |
| 16 | 内核版本 | `uname -r` | 与固定提交中 rockchip 所用的内核版本一致（6.18.y） | |

## kmod 兼容性（任务 8.2）

| # | 操作 | 期望结果 | 结果 |
|---|---|---|---|
| 1 | 用同一次构建的仓库安装一个镜像里没有预装的 kmod，例如 `apk add --allow-untrusted kmod-<x>.apk` | 安装成功，`modprobe` 能加载 | |
| 2 | 改一处内核配置另外构建一次，拿它产出的 kmod 来安装 | apk 因为内核依赖不满足而拒绝 | |
