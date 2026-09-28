# Spec Delta

## Purpose

规定固件内核的版本、eBPF 数据面、容器和存储所需要的内核特性，以及默认的 TCP 拥塞控制算法。

## ADDED Requirements

### Requirement: 内核版本跟随上游
内核版本 SHALL 等于固定下来的上游提交里 rockchip target 默认选用的版本，目前是 6.18.y 系列。

#### Scenario: 检查运行中的内核
- **WHEN** 在设备上查看运行中的内核版本
- **THEN** 版本号与这次构建所固定的上游提交中 rockchip target 选用的内核版本一致

### Requirement: 提供 BTF
内核 MUST 提供自身的 BTF 类型信息（`/sys/kernel/btf/vmlinux`），并为已加载的内核模块提供各自的 BTF。

#### Scenario: 检查 BTF
- **WHEN** 系统启动后查看 `/sys/kernel/btf/`
- **THEN** `vmlinux` 存在且不为空，已加载的模块也有对应的 BTF 文件

### Requirement: BPF 与 cgroup v2
内核 SHALL 启用 BPF 系统调用、BPF JIT、BPF 事件、带 BPF 挂载能力的 cgroup，以及 tcx。系统 SHALL 只挂载统一的 cgroup v2 层级，MUST NOT 启用 v1 的内存控制器。

#### Scenario: 检查 cgroup 挂载
- **WHEN** 系统启动后查看 cgroup 的挂载情况
- **THEN** `/sys/fs/cgroup` 是 cgroup2，并且没有挂载任何 v1 控制器

#### Scenario: 能加载 tcx 程序
- **WHEN** 在某个网口的 tcx 入口挂载一个 BPF 程序
- **THEN** 挂载成功，`bpftool net show` 能列出它

### Requirement: 根文件系统和 overlay 需要的内核功能都编进内核
内核 SHALL 内置 EROFS（包括 lz4 解压），以及带压缩功能（包括 zstd）的 F2FS，不依赖任何可加载模块。

#### Scenario: 不加载任何模块就能启动
- **WHEN** 设备启动
- **THEN** 根文件系统以 erofs 挂载成功，overlay 以 f2fs 带压缩挂载成功，过程中没有加载任何文件系统模块

### Requirement: 同一个内核能在模拟器中启动
内核 SHALL 内置 QEMU `virt` 平台所需的驱动：PL011 串口、通用 PCIe 主机控制器、virtio 块设备和网卡，以及 i6300esb 看门狗。这样出货内核不做任何修改就能在模拟器中启动并使用磁盘、网络和看门狗。这些驱动 MUST 编译进内核，不能作为模块。

#### Scenario: 出货内核在模拟器中启动
- **WHEN** 用从出货镜像中提取出来的内核启动 QEMU `virt` 机器
- **THEN** 串口有输出，virtio 磁盘上的根文件系统被挂载，两块 virtio 网卡和看门狗设备都被识别

### Requirement: 默认拥塞控制为 BBRv3
系统默认的 TCP 拥塞控制 SHALL 是 BBRv3，默认队列规则 SHALL 是 fq。

#### Scenario: 检查拥塞控制设置
- **WHEN** 系统启动后读取 `net.ipv4.tcp_congestion_control` 和 `net.core.default_qdisc`
- **THEN** 两者分别是 `bbr` 和 `fq`，并且 `/proc/kallsyms` 里能找到 `tcp_bbr` 模块中 BBRv3 才有的回调 `bbr_skb_marked_lost` 和 `bbr_tso_segs`（OpenWrt 开启了 `MODULE_STRIPPED`，会去掉 `MODULE_VERSION`，所以看不到模块版本号）

#### Scenario: 本机发起的连接使用 BBR
- **WHEN** 设备自己发起一条 TCP 连接
- **THEN** `ss -ti` 显示这条连接的拥塞控制是 bbr

### Requirement: 内核源码只改 BBRv3
修改内核源码的补丁 SHALL 只有 BBRv3 这一组，MUST NOT 包含 NAT、fullcone、shortcut-fe 或其他转发加速类补丁。

#### Scenario: 审计内核补丁
- **WHEN** 列出补丁队列中所有修改内核源码的补丁
- **THEN** 其中只有 BBRv3 系列

### Requirement: 使用标准 vermagic
内核模块的版本标识（vermagic）SHALL 按上游 OpenWrt 的标准方式计算，MUST NOT 被替换成与内核配置无关的固定值。

#### Scenario: 安装同一次构建的 kmod
- **WHEN** 在设备上安装与镜像出自同一次构建的任意 kmod
- **THEN** 安装成功，模块能正常加载

#### Scenario: 拒绝内核配置不同的 kmod
- **WHEN** 尝试安装一次内核配置不同的构建所产出的 kmod
- **THEN** 包管理器因为内核依赖不满足而拒绝安装
