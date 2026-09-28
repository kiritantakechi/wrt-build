# Spec Delta

## Purpose

为仓库中的全部代码规定统一、强制的规范：格式一致、静态检查通过、脚本结构统一、命名对称，并由一条命令检查、在 CI 中强制执行。

## ADDED Requirements

### Requirement: 统一格式化
仓库中的代码 SHALL 使用固定的格式化工具，并以格式化后的状态提交：
- shell 脚本用 shfmt（POSIX 方言）；
- Nix 用 nixfmt；
- Python 用 ruff format；
- 所有文本文件遵守 `.editorconfig`。

任何一处与格式化结果不一致，都 MUST 使检查失败。

#### Scenario: 提交了未格式化的代码
- **WHEN** 某个 shell 脚本的缩进与 shfmt 的输出不一致
- **THEN** 格式检查失败，并显示需要修改的差异

### Requirement: 静态检查全部通过
仓库中的代码 SHALL 通过以下全部静态检查：
- shellcheck（包括仓库配置中启用的可选检查）；
- ruff check（启用全部规则，只排除有记录的少数几项）；
- ty；
- actionlint；
- 禁止模式检查。

#### Scenario: 引入静态检查告警
- **WHEN** 某个脚本新增了一处 shellcheck 告警
- **THEN** 检查失败，并指出文件、行号和规则编号

### Requirement: 统一的脚本骨架
每个 shell 脚本 SHALL 按相同的顺序组织：
1. 用一行说明脚本做什么，以及用法；
2. 开启严格模式；
3. 引入公共函数库；
4. 参数解析；
5. 前置检查（宿主机、构建目录、构建环境）；
6. 主体逻辑。

#### Scenario: 新增脚本
- **WHEN** 新增一个脚本
- **THEN** 它的开头结构与已有脚本相同，缺少某个部分时检查会报告出来

### Requirement: 对称命名
- 有逆操作的操作 SHALL 成对出现，并使用对称的名字，例如 mount/unmount、pack/unpack、up/down。
- just 命令名 SHALL 与对应的脚本名一致。
- 针对具体对象的脚本 SHALL 按“对象-动词”命名；流水线阶段的脚本用单独的动词命名。
- 环境变量 SHALL 统一以 `WRT_` 作为前缀。

#### Scenario: 只有一半的操作
- **WHEN** 仓库里存在一个挂载构建目录的命令
- **THEN** 同时存在对应的卸载命令，两者的命名对称

### Requirement: 一条命令检查和格式化
`just check` SHALL 以只检查、不修改的方式运行全部格式化工具和静态检查；`just fmt` SHALL 对全部文件执行格式化。两者都 SHALL 能在 macOS 和 Linux 上运行。CI SHALL 在每次推送时运行 `just check`，不通过就失败。

#### Scenario: 检查后再格式化
- **WHEN** 先执行 `just fmt`，再执行 `just check`
- **THEN** `just check` 中与格式有关的检查全部通过
