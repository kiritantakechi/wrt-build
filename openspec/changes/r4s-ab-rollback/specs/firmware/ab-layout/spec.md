# Spec Delta

## Purpose

规定 SD 卡上的双系统分区布局，以及出厂镜像和单槽升级镜像这两种产物的格式，为不停机升级和自动回滚打基础。

## ADDED Requirements

### Requirement: 四分区双槽布局
SD 卡 SHALL 使用 MBR 分区表，依次包含四个主分区：boot-A、root-A、boot-B、root-B。U-Boot 和它的环境变量 SHALL 放在第一个分区之前的保留区域。每个 root 分区里 SHALL 是一份 EROFS 根文件系统，后面紧跟属于这个槽位自己的 overlay。

#### Scenario: 检查分区表
- **WHEN** 刷入出厂镜像后查看 SD 卡的分区表
- **THEN** 能看到四个主分区，按 boot-A、root-A、boot-B、root-B 的顺序排列，第一个分区之前留有 U-Boot 和环境变量的空间

### Requirement: 出厂镜像
出厂镜像 SHALL 同时包含 A、B 两个槽位，两个槽位里是同一个版本的系统。刷入出厂镜像后首次启动 SHALL 进入槽位 A。

#### Scenario: 首次启动
- **WHEN** 把出厂镜像写入 SD 卡后上电
- **THEN** 系统从槽位 A 启动

#### Scenario: 槽位 B 同样可用
- **WHEN** 刷入出厂镜像后手动切换到槽位 B
- **THEN** 系统能从槽位 B 正常启动

### Requirement: 单槽升级镜像
升级镜像 SHALL 只包含一个槽位的 boot 分区内容和 root 分区内容，以及用来确认目标设备的元数据。升级镜像 MUST NOT 包含 U-Boot、U-Boot 环境变量或分区表。

#### Scenario: 检查升级镜像内容
- **WHEN** 列出升级镜像里的内容
- **THEN** 只有 boot 内容、root 内容和元数据，没有引导程序，也没有分区表

### Requirement: 4 GB 的 SD 卡放得下
整个布局 SHALL 能完整放进一张 4 GB 的 microSD 卡。

#### Scenario: 写入 4 GB 卡
- **WHEN** 把出厂镜像写入一张 4 GB 的 microSD 卡
- **THEN** 写入成功，两个槽位都能启动
