# Spec Delta

## Purpose

决定每次启动用哪个槽位；新系统连续启动都没能被确认时，自动退回另一个槽位；把内核卡死和内核 panic 转成可以计数的重启。

## ADDED Requirements

### Requirement: 按持久变量选择槽位
引导程序 SHALL 按持久保存的 `boot_slot` 变量启动对应槽位。这个变量不存在或值无效时 SHALL 启动槽位 A。当前槽位 SHALL 通过内核命令行传给 Linux。

#### Scenario: 选择槽位 B
- **WHEN** `boot_slot` 为 `b` 时启动
- **THEN** 根文件系统来自 root-B，内核命令行里标明当前槽位是 b

#### Scenario: 持久变量缺失或已损坏
- **WHEN** 持久环境里没有 `boot_slot`，或者整块环境变量已损坏
- **THEN** 系统从槽位 A 启动

### Requirement: 启动逻辑不能被持久环境覆盖
只有 `boot_slot`、`bootcount`、`upgrade_available` 这几个运行时变量 SHALL 从持久环境读取。选槽和回滚逻辑 MUST 来自引导程序本身，不能被持久环境里的同名变量替换。

#### Scenario: 持久环境里写入了自定义启动命令
- **WHEN** 有人往持久环境里写入一条自定义的启动命令后重启
- **THEN** 引导程序仍然使用自己内置的选槽逻辑

### Requirement: 试运行计数与自动回滚
`upgrade_available` 为 1 时，每次启动 SHALL 把 `bootcount` 加一。`bootcount` 超过 3 时，引导程序 SHALL 把 `boot_slot` 切换到另一个槽位，清除 `upgrade_available` 和 `bootcount`，然后启动那个槽位。`upgrade_available` 为 0 时 MUST NOT 增加 `bootcount`，也 MUST NOT 为了计数而写 SD 卡。

#### Scenario: 新槽位连续启动失败
- **WHEN** 新槽位处于试运行状态，并且连续三次启动都没有被确认
- **THEN** 第四次启动时引导程序切回原来的槽位，并且 `upgrade_available` 被清为 0

#### Scenario: 正常运行时不计数
- **WHEN** `upgrade_available` 为 0 时重启
- **THEN** `bootcount` 保持不变，引导程序没有写入环境变量

#### Scenario: 当前槽位加载失败
- **WHEN** 当前槽位的内核无法加载
- **THEN** 引导程序在同一次上电中改为尝试另一个槽位；两个槽位都失败时停在引导程序里，不会无限循环

### Requirement: 卡死和 panic 都会变成重启
硬件看门狗 SHALL 在内核开始运行前启动，并一直保持工作，直到用户态接管。用户态在规定时间内没有接管时，看门狗 SHALL 让设备复位。内核 panic 后 SHALL 在 10 秒内自动重启。

#### Scenario: 内核 panic
- **WHEN** 系统运行中触发内核 panic
- **THEN** 设备在 10 秒内重启；如果当时处于试运行状态，`bootcount` 加一

#### Scenario: 启动早期卡死
- **WHEN** 内核在用户态启动之前卡住
- **THEN** 看门狗超时后设备复位

#### Scenario: 用户态迟迟没有接管
- **WHEN** 内核启动了，但用户态在规定时间内一直没有打开看门狗
- **THEN** 设备复位
