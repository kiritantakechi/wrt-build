# Spec Delta

## Purpose

规定怎样才算“新系统启动成功”：成功就确认当前槽位；试运行期间失败就重启，让引导程序的计数往前推进，最终回滚。

## ADDED Requirements

### Requirement: 内置检查项
启动后，健康检查 SHALL 核对以下各项：用户态已经启动完成；br-lan 已经起来并配好地址；dropbear 在 LAN 地址上监听；uhttpd 在 LAN 地址上监听；所有已注册的组件检查项都通过。WAN 的状态 MUST NOT 作为判定条件。

#### Scenario: WAN 断开但其他正常
- **WHEN** 试运行期间 PPPoE 拨不上，其他检查项都正常
- **THEN** 健康检查判定为成功

#### Scenario: Web 服务没有起来
- **WHEN** uhttpd 在检查时限内一直没有在 LAN 地址上监听
- **THEN** 健康检查判定为失败

### Requirement: 组件可以注册检查项
其他组件 SHALL 能通过把检查程序安装到一个约定目录来注册额外的检查项。每个检查项返回“通过”或“失败”。任一检查项失败，或者超过单项时限还没返回，整体 MUST 判定为失败。

#### Scenario: 注册的检查项失败
- **WHEN** 某个组件注册的检查项返回失败
- **THEN** 健康检查判定为失败，结果里写明是哪一项失败

#### Scenario: 检查项超时
- **WHEN** 某个检查项超过单项时限仍未返回
- **THEN** 这一项按失败处理，整体也判定为失败

### Requirement: 按是否处于试运行分别处理结果
如果处于试运行状态（`upgrade_available` 为 1）：
- 检查在总时限内通过时，SHALL 把 `bootcount` 清零，并把 `upgrade_available` 清为 0，也就是确认当前槽位；
- 检查失败或者超出总时限时，SHALL 重启设备。

如果系统已经确认过，检查失败时 SHALL 只记录结果，MUST NOT 重启。

#### Scenario: 试运行时检查通过
- **WHEN** 试运行状态下健康检查通过
- **THEN** `upgrade_available` 变成 0，`bootcount` 变成 0，后续重启都继续使用这个槽位

#### Scenario: 试运行时检查失败
- **WHEN** 试运行状态下健康检查失败
- **THEN** 设备重启

#### Scenario: 已确认的系统检查失败
- **WHEN** 系统已经确认过，健康检查失败
- **THEN** 失败结果被记录下来，设备不重启

### Requirement: 可以查询槽位状态
管理员 SHALL 能用一条命令查到：当前槽位、它是否已经确认、最近一次健康检查的结果，以及失败的检查项。

#### Scenario: 查询状态
- **WHEN** 管理员执行槽位状态查询命令
- **THEN** 输出里有当前槽位（a 或 b）、是否已确认、最近一次检查的时间和结果，失败时还列出失败的检查项
