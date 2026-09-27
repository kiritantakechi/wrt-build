# Spec Delta

## Purpose

在公开仓库的 GitHub 托管 runner 上分阶段自动完成完整构建，并保证发布出去的镜像和 kmod 仓库出自同一次构建。

## ADDED Requirements

### Requirement: 分阶段构建，每个 job 都在时限内
CI SHALL 把构建拆成“宿主工具与工具链”和“固件”两个阶段。每个 job MUST 在 GitHub 托管 runner 的 6 小时上限内完成，并以 5 小时作为内部目标，留出余量。

#### Scenario: 冷缓存构建
- **WHEN** 在没有任何缓存的情况下运行 CI
- **THEN** 所有 job 都在 6 小时内完成，并产出固件镜像和软件包仓库

#### Scenario: 工具链缓存命中
- **WHEN** 影响工具链的输入都没有变化
- **THEN** 工具链阶段直接复用缓存，固件阶段在缓存的工具链上继续构建

### Requirement: 按实际输入确定缓存
工具链阶段的缓存键 SHALL 只由会影响它的输入决定：openwrt 仓库里工具和工具链相关的目录内容、工具链相关的配置、`flake.lock`。固件阶段 SHALL 使用编译缓存加速重复编译。

#### Scenario: 只更新 packages feed
- **WHEN** 只修改了 `upstream.lock` 里 packages feed 的 SHA
- **THEN** 工具链阶段的缓存仍然命中

#### Scenario: 工具链输入变化
- **WHEN** openwrt 仓库的工具链相关目录发生变化
- **THEN** 工具链缓存失效，并被重新构建

### Requirement: 产出全部 kmod
固件阶段 SHALL 构建全部内核模块包，并把它们放进同一次构建产出的软件包仓库。

#### Scenario: 仓库里有全部 kmod
- **WHEN** 固件阶段完成
- **THEN** 软件包仓库里包含这次构建能生成的全部 `kmod-*` 包，它们依赖的内核版本标识和镜像内核一致

### Requirement: 镜像与 kmod 出自同一次构建
每次构建 SHALL 输出一份清单，至少记录：构建运行标识、`upstream.lock` 的哈希、内核版本标识（vermagic），以及镜像和软件包索引的校验和。镜像和软件包仓库 MUST 作为一个整体交给后续的发布流程。

#### Scenario: 清单完整
- **WHEN** 一次构建成功结束
- **THEN** 产物里有这份清单，其中记录的 vermagic 与镜像内核、仓库里的 kmod 一致

### Requirement: 构建阶段不需要任何密钥
公开仓库里的构建阶段 MUST NOT 依赖任何仓库密钥，也 MUST NOT 有权读取签名密钥。

#### Scenario: fork 仓库运行 CI
- **WHEN** 在一个没有配置任何密钥的 fork 仓库里运行 CI
- **THEN** 两个构建阶段都能成功完成，并产出没有签名的构建产物
