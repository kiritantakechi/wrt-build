# Spec Delta

## Purpose

规定目标软件包用哪个编译器版本、哪个链接器和哪些优化参数，让整机针对 RK3399 的 A72 + A53 大小核组合做优化。

## ADDED Requirements

### Requirement: 目标工具链版本
目标工具链 SHALL 使用 GCC 15 和 musl libc。

#### Scenario: 检查工具链版本
- **WHEN** 查看构建出的目标交叉编译器版本
- **THEN** GCC 主版本号是 15，C 库是 musl

### Requirement: 针对大小核的优化参数
目标用户态软件包 SHALL 使用 `-O2` 和 `-mcpu=cortex-a72.cortex-a53+crypto` 编译，并且这两个参数 MUST 排在默认的 `-Os` 和通用 CPU 参数之后，让它们最终生效。只有明确声明退出的软件包可以例外。

#### Scenario: 检查编译命令
- **WHEN** 查看任意一个没有声明退出的目标用户态软件包的实际编译命令
- **THEN** 命令里带有 `-O2 -mcpu=cortex-a72.cortex-a53+crypto`，并且位置在 `-Os` 之后

### Requirement: 默认开启 LTO、mold 和 gc-sections
目标软件包 SHALL 默认使用链接时优化（LTO）、mold 链接器和按段回收未用代码（gc-sections）。开了这些选项就构建失败的软件包 MUST 在它自己的构建定义里单独退出对应选项，而不能全局关闭。

#### Scenario: 个别软件包不兼容 LTO
- **WHEN** 某个软件包在 LTO 下构建失败
- **THEN** 只有这个软件包关闭 LTO，退出记录在它的包定义或对应补丁里，其他软件包仍然使用 LTO

### Requirement: 只靠配置实现优化，不改构建系统
上面这些工具链和优化设置 SHALL 全部通过构建配置实现，MUST NOT 修改上游构建系统里定义默认编译参数的文件（`include/target.mk`）。

#### Scenario: 审计补丁队列
- **WHEN** 列出 openwrt 补丁队列里被修改的文件
- **THEN** 其中不包括 `include/target.mk`
