# Spec Delta

## Purpose

规定固件的出厂默认值和基础使用体验：管理地址、Web 管理界面、界面语言、交互 shell、内存压缩和密码策略，以及明确不包含的组件。

## ADDED Requirements

### Requirement: LAN 默认地址
在没有保留配置的情况下，LAN 的默认地址 SHALL 是 10.0.0.1/24，故障安全模式（failsafe）下的地址也 SHALL 是 10.0.0.1。保留配置升级时 MUST NOT 覆盖用户自己设置的 LAN 地址。

#### Scenario: 全新安装
- **WHEN** 刷入镜像后第一次启动，没有任何保留配置
- **THEN** br-lan 的地址是 10.0.0.1/24

#### Scenario: 进入故障安全模式
- **WHEN** 设备进入故障安全模式
- **THEN** 可以通过 10.0.0.1 访问设备

#### Scenario: 保留配置升级
- **WHEN** 用户把 LAN 地址改成别的地址后，做了一次保留配置的升级
- **THEN** 升级后 LAN 地址仍然是用户设置的那个

### Requirement: Web 管理界面
LuCI SHALL 由 uhttpd 配合 ucode 提供，默认界面语言 SHALL 是简体中文。镜像 MUST NOT 包含 nginx 或 uwsgi。

#### Scenario: 访问管理界面
- **WHEN** 在 LAN 上用浏览器访问 `http://10.0.0.1`
- **THEN** 由 uhttpd 返回 LuCI 页面，界面语言为简体中文

#### Scenario: 不包含 nginx 和 uwsgi
- **WHEN** 列出镜像里安装的软件包
- **THEN** 其中没有 nginx，也没有 uwsgi

### Requirement: 交互 shell
root 的登录 shell SHALL 是 `/bin/ash`。交互式登录会话在 zsh 可用时 SHALL 自动切换到 zsh，并加载 autosuggestions 和 syntax-highlighting 两个插件；zsh 不可用时 MUST 留在 ash。非交互式执行命令时 MUST NOT 启动 zsh。镜像 SHALL 同时提供 bash，用户可以手动进入；以登录方式启动的 bash MUST NOT 被切换到 zsh。

#### Scenario: SSH 交互登录
- **WHEN** 通过 SSH 以 root 交互方式登录
- **THEN** 进入 zsh 会话，两个插件都已加载

#### Scenario: 非交互执行命令
- **WHEN** 通过 SSH 远程执行一条命令，不分配终端
- **THEN** 命令由 ash 执行，不启动 zsh

#### Scenario: zsh 不可用
- **WHEN** zsh 可执行文件不存在或无法执行
- **THEN** 交互登录仍然成功，停留在 ash

#### Scenario: 手动进入 bash
- **WHEN** 登录后执行 `bash -l`
- **THEN** 进入 bash 会话，并且不会被切换到 zsh

### Requirement: 内存压缩交换
系统 SHALL 提供一个 1 GiB、用 zstd 压缩的 zram 交换设备。

#### Scenario: 检查交换设备
- **WHEN** 系统启动完成后查看交换设备
- **THEN** 存在一个 1 GiB 的 zram 交换设备，压缩算法是 zstd

### Requirement: 镜像不预置密码
镜像 MUST NOT 包含任何预置的 root 密码哈希。管理员 SHALL 在首次使用时自己设置密码。

#### Scenario: 检查影子密码文件
- **WHEN** 查看镜像里的 `/etc/shadow`
- **THEN** root 条目没有密码哈希

### Requirement: 不包含的组件
镜像 MUST NOT 包含以下组件：用 UPX 压缩过的可执行文件、LRNG、urngd、shortcut-fe、natflow、PCRE1 库、opkg。

#### Scenario: 检查安装的软件包和可执行文件
- **WHEN** 列出镜像里的软件包，并扫描可执行文件
- **THEN** 以上组件都不存在，也没有任何可执行文件带 UPX 标记
