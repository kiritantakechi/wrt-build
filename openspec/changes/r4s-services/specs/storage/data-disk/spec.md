# Spec Delta

## Purpose

规定 USB SSD 数据盘的文件系统、子卷布局和挂载方式；依赖数据盘的服务怎样等盘就绪再启动；持久日志放在哪里；以及数据盘缺失时如何降级，好让写入较重的负载都不落在 SD 卡上。

## ADDED Requirements

### Requirement: btrfs 数据盘与子卷布局
数据盘 SHALL 使用 btrfs，并包含 `@containers`、`@downloads`、`@shares`、`@logs` 四个子卷，另有一个 `.snapshots` 子卷用于存放快照。每个子卷 SHALL 挂载到各自固定的挂载点，挂载选项包含 zstd 压缩和 noatime。

#### Scenario: 检查挂载
- **WHEN** 接上已经初始化好的数据盘并启动系统
- **THEN** 四个子卷分别挂载在固定的挂载点上，挂载选项里有 `compress=zstd` 和 `noatime`

### Requirement: 按 UUID 识别数据盘
数据盘 SHALL 按文件系统 UUID 识别并挂载，与 USB 口的位置和设备名无关。UUID 不匹配的磁盘 MUST NOT 被挂载到数据盘的挂载点上。

#### Scenario: 换一个 USB 口
- **WHEN** 把数据盘从一个 USB 口换到另一个口后重启
- **THEN** 各个子卷仍然挂载在原来的挂载点上

#### Scenario: 插入另一块磁盘
- **WHEN** 插入一块 UUID 不同的磁盘
- **THEN** 它不会被挂载到数据盘的挂载点上

### Requirement: 依赖数据盘的服务等挂载完成再启动
依赖数据盘的服务（容器、文件共享、下载）SHALL 在对应的挂载点可用之后才启动，挂载点重新出现时 SHALL 重新启动这些服务。它们 MUST NOT 在挂载点不存在时把数据写到 SD 卡上。

#### Scenario: 数据盘挂载得比较晚
- **WHEN** 系统启动时数据盘晚了 30 秒才挂载上
- **THEN** 容器和文件共享服务在挂载完成后才开始运行，SD 卡上的同名目录里没有新写入的数据

### Requirement: 数据盘缺失时降级
数据盘不在时，依赖它的服务 SHALL 不启动，路由、防火墙、NAT、代理、DNS 和 VPN MUST 照常工作。

#### Scenario: 不接数据盘启动
- **WHEN** 不接数据盘时启动系统
- **THEN** LAN 客户端可以正常上网，容器和文件共享服务没有运行，健康检查仍然通过

### Requirement: 持久日志写到数据盘
系统日志 SHALL 在数据盘可用时持续写入 `@logs`，达到大小上限时轮转。SD 卡上 MUST NOT 保存持久日志。

#### Scenario: 重启后查看日志
- **WHEN** 系统运行一段时间后重启
- **THEN** 重启之前的日志仍然保存在 `@logs` 中

### Requirement: 定期只读快照
`@containers` 和 `@shares` SHALL 每天生成一份只读快照，保存到 `.snapshots`，保留最近 7 天。管理员 SHALL 能随时手动生成一份快照。

#### Scenario: 过期快照被清理
- **WHEN** 系统已经运行超过 8 天
- **THEN** `.snapshots` 里这两个子卷各自只保留最近 7 份每日快照

#### Scenario: 手动快照
- **WHEN** 管理员执行手动快照命令
- **THEN** `.snapshots` 里出现一份带当前时间戳的只读快照
