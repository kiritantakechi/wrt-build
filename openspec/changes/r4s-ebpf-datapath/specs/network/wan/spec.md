# Spec Delta

## Purpose

规定 WAN 侧的行为：PPPoE 拨号、TCP MSS 钳制、IPv6 前缀下发与防火墙，以及软件转发加速。

## ADDED Requirements

### Requirement: PPPoE 拨号
WAN SHALL 通过 eth0 做 PPPoE 拨号。拨号凭据 SHALL 在运行时提供，MUST NOT 预置在固件镜像里。

#### Scenario: 镜像不含凭据
- **WHEN** 检查固件镜像里的网络配置
- **THEN** WAN 是 PPPoE 类型，用户名和密码都为空

#### Scenario: 推送凭据后拨号
- **WHEN** 把拨号凭据推送到设备上
- **THEN** pppoe-wan 接口起来，并获得 ISP 分配的 IPv4 地址

### Requirement: MSS 钳制
经 WAN 转发的 TCP 连接，其 SYN 报文中的 MSS SHALL 被钳制到与路径 MTU 相符的值。

#### Scenario: 内网主机建立 TCP 连接
- **WHEN** 一台 LAN 主机经 WAN 建立 TCP 连接
- **THEN** 对端收到的 MSS 不超过 1452

### Requirement: IPv6 前缀下发
路由器 SHALL 通过 PPPoE 上的 DHCPv6-PD 获得 IPv6 前缀，并通过 RA 和 DHCPv6 分配给 LAN。LAN 主机 SHALL 获得全局 IPv6 地址，并且 MUST NOT 经过 NAT66。

#### Scenario: LAN 主机获得 IPv6
- **WHEN** 一台 LAN 主机接入网络
- **THEN** 它获得前缀内的全局 IPv6 地址，并能访问 IPv6 外网

### Requirement: IPv6 入站防火墙
从 WAN 进入 LAN 的 IPv6 新连接 SHALL 默认被拒绝，只有显式放行的规则除外。

#### Scenario: 外部主动连接内网 IPv6 地址
- **WHEN** 一台外部主机向某台 LAN 主机的全局 IPv6 地址主动发起 TCP 连接
- **THEN** 连接被拒绝

### Requirement: 软件转发加速不绕过地址转换
软件 flowtable SHALL 启用。已经被加速的流 MUST 仍然经过 einat 的地址转换。

#### Scenario: 下载期间检查加速和源地址
- **WHEN** 一台 LAN 主机持续下载时，查看 flowtable 的加速情况和外部看到的源地址
- **THEN** 这条流被加速处理，外部看到的源地址始终是路由器的 WAN 地址
