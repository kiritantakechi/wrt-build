# Spec Delta

## Purpose

规定运行时配置和密钥的存放方式，以及怎样推送到设备并生效：密钥加密保存在私有仓库里，推送前先校验，失败就回滚，配置跨 A/B 升级保留。

## ADDED Requirements

### Requirement: 密钥加密存放
私有配置仓库里的密钥（PPPoE 凭据、dae 订阅和节点、WireGuard 私钥、Tailscale 认证密钥、SMB 用户凭据）SHALL 以加密形式提交。明文只 SHALL 临时出现在执行推送的工作站内存或临时目录里，以及设备上。

#### Scenario: 扫描私有仓库
- **WHEN** 用密钥扫描工具检查私有配置仓库的全部历史
- **THEN** 找不到任何明文密钥

### Requirement: 推送前先校验
推送工具 SHALL 在修改设备之前，先校验全部待推送的配置，包括 dae 配置的语法和 UCI 配置的语法。校验失败时，设备上 MUST NOT 有任何改动。

#### Scenario: dae 配置有语法错误
- **WHEN** 推送一份有语法错误的 dae 配置
- **THEN** 推送在修改设备之前就中止，设备上原有的配置和服务都保持不变

### Requirement: 推送结果可重复
重复推送同一份配置 SHALL 得到相同的结果，并且 MUST NOT 重启配置没有变化的服务。

#### Scenario: 重复推送
- **WHEN** 连续两次推送同一份配置
- **THEN** 第二次推送没有重启任何服务

### Requirement: 服务启动失败时回滚
配置写入之后，如果某个服务重载失败，推送工具 SHALL 恢复这个服务推送前的配置并再次重载，然后报告失败。

#### Scenario: 服务重载失败
- **WHEN** 新配置能通过校验，但对应服务重载失败
- **THEN** 该服务恢复到推送前的配置并正常运行，推送工具返回非零并说明原因

### Requirement: 配置跨 A/B 升级保留
推送到设备的配置和密钥 SHALL 包含在升级时的配置备份里，切换槽位后仍然存在。

#### Scenario: 升级到另一个槽位
- **WHEN** 推送配置后做一次保留配置的升级
- **THEN** 新槽位里 PPPoE、dae、WireGuard、Tailscale 和 SMB 的配置都还在

### Requirement: dae 用户配置不能指定绑定接口
推送工具 MUST 拒绝包含 `lan_interface` 或 `wan_interface` 的 dae 用户配置，因为这两项由固件自动生成。

#### Scenario: 用户配置里写了 lan_interface
- **WHEN** 推送一份在用户配置里写了 `lan_interface` 的 dae 配置
- **THEN** 推送在校验阶段失败，并提示这个字段由固件管理

### Requirement: 只用 SSH 密钥认证
推送 SHALL 通过 SSH 密钥认证连接设备，MUST NOT 使用密码认证。

#### Scenario: 没有配置 SSH 密钥
- **WHEN** 设备上没有部署推送用的公钥时尝试推送
- **THEN** 推送因为认证失败而中止，不会退回去用密码登录
