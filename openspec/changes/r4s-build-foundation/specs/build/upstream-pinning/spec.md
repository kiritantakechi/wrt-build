# Spec Delta

## Purpose

保证每次构建用到的上游源码、feeds 和补丁完全由仓库内容决定，可以复现；任何补丁失效都会在构建开始前立刻暴露。

## ADDED Requirements

### Requirement: 上游源码固定到提交
openwrt、packages、luci 三个上游仓库 SHALL 按 `upstream.lock` 里记录的 URL 和提交 SHA 获取。构建 MUST NOT 使用分支 HEAD 或标签的当前指向。

#### Scenario: 同一份 lock 得到同一份源码
- **WHEN** 在同一份 `upstream.lock` 下，于不同时间、不同机器上分别获取源码
- **THEN** 三个仓库检出的提交 SHA 都和 lock 中的记录一致

#### Scenario: feeds 配置也固定到提交
- **WHEN** 生成 feeds 配置
- **THEN** 每个 feed 条目都带有 lock 里的提交 SHA，不引用任何分支名

### Requirement: 补丁按顺序应用，失败即停止
对上游的所有修改 SHALL 以补丁文件的形式存放在仓库里，并按各上游仓库分目录、按文件名顺序应用。任何一个补丁无法干净应用时，构建 MUST 中止，并报出这个补丁的文件名。

#### Scenario: 补丁冲突
- **WHEN** 上游更新后，某个补丁无法干净应用
- **THEN** 构建中止并指出冲突的补丁文件，不继续生成配置，也不产出任何东西

#### Scenario: 补丁全部应用成功
- **WHEN** 所有补丁都能干净应用
- **THEN** 得到的源码树内容只取决于 `upstream.lock` 和补丁文件本身，与应用补丁的时间无关

### Requirement: 构建过程中不拉取远程脚本，也不就地改上游文本
构建过程 MUST NOT 从网络下载脚本或补丁来执行或应用，也 MUST NOT 用就地文本替换（例如 `sed -i`）修改上游文件。上游软件包的源码包 SHALL 通过带哈希校验的下载获取。

#### Scenario: 审计构建脚本
- **WHEN** 检查仓库里的全部构建脚本和 CI 工作流
- **THEN** 找不到下载并执行或应用远程脚本、补丁的命令，也找不到对上游源码树的就地文本替换

### Requirement: 构建时间戳可复现
构建使用的 `SOURCE_DATE_EPOCH` SHALL 等于 `upstream.lock` 中 openwrt 那个提交的提交时间，与补丁在什么时候应用无关。

#### Scenario: 不同时间构建同一份 lock
- **WHEN** 在不同日期对同一份 `upstream.lock` 和同一组补丁各构建一次
- **THEN** 两次构建使用的 `SOURCE_DATE_EPOCH` 相同，镜像里记录的构建日期也相同
