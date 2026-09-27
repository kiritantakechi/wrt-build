# Spec Delta

## Purpose

规定每次发布的内容、存放位置和组织方式；区分候选版和正式版；保证同一次发布里的产物出自同一次构建。

## ADDED Requirements

### Requirement: 每次签名产出一个 Release
每次签名完成后 SHALL 在 GitHub 上生成一个 Release，其中包含：签名后的出厂镜像、签名后的单槽升级镜像、包含同一次构建全部软件包和 kmod 的仓库归档、构建清单，以及各产物的校验和。

#### Scenario: 检查 Release 内容
- **WHEN** 查看一个已发布的 Release
- **THEN** 其中有出厂镜像、升级镜像、仓库归档、构建清单和校验和文件，清单里的 vermagic 与仓库中 kmod 所依赖的内核版本标识一致

### Requirement: 候选版与正式版
来自 bump PR 的构建 SHALL 以预发布（候选版）的形式发布；合并进主分支之后的构建 SHALL 以正式版发布。

#### Scenario: PR 构建
- **WHEN** 一个 bump PR 的构建完成签名
- **THEN** 它以预发布的形式出现，而不会成为最新的正式版

#### Scenario: 合并后构建
- **WHEN** PR 合并后主分支的构建完成签名
- **THEN** 它以正式版发布，成为最新的正式版

### Requirement: 产物必须出自同一次构建
如果镜像和仓库归档来自不同的构建运行（构建清单中的运行标识不一致），发布 MUST 失败。

#### Scenario: 混用了两次构建的产物
- **WHEN** 发布流程收到的镜像和仓库归档出自两次不同的构建
- **THEN** 发布失败，不创建 Release

### Requirement: 发布说明可追溯
Release 的说明 SHALL 列出这次构建所用的 `upstream.lock` 中三个上游仓库的 SHA，以及补丁队列的哈希。

#### Scenario: 查看发布说明
- **WHEN** 打开一个 Release 的说明
- **THEN** 能看到 openwrt、packages、luci 的 SHA，以及补丁队列的哈希
