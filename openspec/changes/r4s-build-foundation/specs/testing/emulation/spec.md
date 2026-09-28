# Spec Delta

## Purpose

在 QEMU 中以 R4S 的身份启动出货镜像本身，并提供可重复的网络拓扑和故障注入，使大部分功能不需要真机就能验证。

## ADDED Requirements

### Requirement: 启动的是出货产物
模拟器 SHALL 启动出货的 sysupgrade 镜像本身：
- 内核从镜像 boot 分区里的 FIT 中提取；
- 磁盘就是这个镜像；
- 内核启动参数取自镜像里的 `boot.scr`，只替换串口设备和根分区标识这两个与硬件相关的部分。

模拟器 MUST NOT 使用另外单独构建的内核或根文件系统。

#### Scenario: 核对产物来源
- **WHEN** 启动一次模拟
- **THEN** 日志记录下所用镜像和内核的 sha256，它们与构建清单中的值一致；启动参数里包含 `boot.scr` 中的 `fstools_overlay_compression_type=zstd`

### Requirement: 以 R4S 的板型身份启动
模拟的机器 SHALL 以 `friendlyarm,nanopi-r4s` 作为板型标识启动，使板级脚本、网口角色分配和升级镜像的板型校验走与真机相同的路径。

#### Scenario: 读取板型
- **WHEN** 在模拟器中读取系统的板型信息
- **THEN** 板型名称是 `friendlyarm,nanopi-r4s`

### Requirement: 指令集与真机一致
模拟的 CPU SHALL 支持镜像编译所针对的指令集（Cortex-A72，带 crypto 扩展），使用户态程序可以原样运行。

#### Scenario: 运行用户态程序
- **WHEN** 在模拟器中运行镜像里的程序
- **THEN** 程序正常运行，没有出现非法指令错误

### Requirement: 可重复的网络拓扑
模拟器 SHALL 提供与 R4S 相同角色的两个网口（WAN、LAN），分别连接到彼此隔离的网络命名空间，其中可以运行“上游网络”和“局域网客户端”。整个拓扑 SHALL 在没有 root 权限的情况下建立。

#### Scenario: 局域网客户端获得地址
- **WHEN** 模拟器启动完成后，局域网命名空间里的客户端请求 DHCP
- **THEN** 客户端获得 10.0.0.0/24 网段里的地址，并能访问 10.0.0.1

#### Scenario: 不需要 root 权限
- **WHEN** 以普通用户身份启动模拟测试
- **THEN** 拓扑和虚拟机都能建立起来，不需要 sudo

### Requirement: 故障注入
模拟器 SHALL 提供以下故障注入手段：
- 强制断电（立即终止虚拟机）；
- 硬件看门狗设备；
- 在启动过程中向串口输入按键；
- 在用例之间把磁盘还原到初始状态。

#### Scenario: 用例之间互不影响
- **WHEN** 一个用例修改了配置，然后下一个用例开始
- **THEN** 下一个用例看到的磁盘是镜像的初始状态

#### Scenario: 强制断电
- **WHEN** 用例在系统运行中强制断电后重新启动虚拟机
- **THEN** 虚拟机从同一块磁盘重新启动，断电前已经写入磁盘的内容仍在
