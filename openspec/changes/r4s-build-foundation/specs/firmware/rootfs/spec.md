# Spec Delta

## Purpose

规定根分区里文件系统的格式和行为：只读、压缩的 EROFS 根文件系统，加上一层写入时压缩的 f2fs overlay。

## ADDED Requirements

### Requirement: 根文件系统使用 EROFS
固件镜像的根文件系统 SHALL 是用 lz4hc 压缩的 EROFS。构建 MUST NOT 生成 squashfs 或 ext4 的根文件系统镜像。

#### Scenario: 检查构建产物
- **WHEN** 查看构建产物目录
- **THEN** 只有基于 EROFS 的镜像，没有 squashfs 或 ext4 根文件系统镜像

#### Scenario: 检查设备上的挂载
- **WHEN** 设备启动后查看挂载信息
- **THEN** 只读根（`/rom`）的文件系统类型是 erofs

### Requirement: 可写层是开启 zstd 压缩的 f2fs
可写的 overlay SHALL 位于同一个根分区里、紧跟在 EROFS 之后，使用带压缩特性格式化的 f2fs，并以 zstd 压缩挂载。

#### Scenario: 首次启动建立 overlay
- **WHEN** 新刷入的镜像第一次启动
- **THEN** `/overlay` 被创建为 f2fs，挂载选项里包含 zstd 压缩

### Requirement: 恢复出厂只清空可写层
恢复出厂设置 SHALL 只清空 overlay，EROFS 根文件系统的内容 MUST 保持不变。

#### Scenario: 恢复出厂
- **WHEN** 执行恢复出厂设置并重启
- **THEN** 配置回到出厂状态，重新建立空的 overlay，EROFS 内容与刷入时完全一致

### Requirement: 镜像能直接启动
构建产出的 SD 卡镜像 SHALL 在写入 microSD 卡后，让 NanoPi R4S 4GB 直接启动到用户态，不需要任何手工步骤。

#### Scenario: 刷写后启动
- **WHEN** 把镜像写入 microSD 卡，插进 R4S 上电
- **THEN** 系统启动完成，LAN 口可以访问管理界面
