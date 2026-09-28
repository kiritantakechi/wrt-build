# Spec Delta

## Purpose

用 einat 在 PPPoE 出口上实现 IPv4 完全锥形 NAT；靠打标只放行 einat 还原过的入站连接；einat 不可用时自动回落到内核的 masquerade。

## ADDED Requirements

### Requirement: 完全锥形 NAT44
LAN 发出的 IPv4 TCP、UDP、ICMP 流量 SHALL 由 einat 做地址转换，映射和过滤都与外部端点无关（EIM + EIF）。

#### Scenario: 映射与外部端点无关
- **WHEN** 同一个内网 socket 先后访问两个不同的外部地址
- **THEN** 两个外部地址看到的是同一个公网端口

#### Scenario: 过滤与外部端点无关
- **WHEN** 映射已经建立后，一个从未被访问过的外部地址向这个公网端口发包
- **THEN** 包被送达对应的内网 socket

### Requirement: 只放行 einat 还原过的入站新连接
从 WAN 转发到 LAN 的新连接 SHALL 只有带 einat 还原标记的报文才被放行。其他从 WAN 进入、目的地址是内网地址的新连接 MUST 被丢弃。

#### Scenario: 伪造目的地址的入站包
- **WHEN** WAN 侧的邻居主机直接发送一个目的地址是内网 IP、且与任何映射都无关的新连接
- **THEN** 这个包被丢弃，内网主机收不到

#### Scenario: 已映射端口的入站包
- **WHEN** 外部主机向一个已建立映射的公网端口发起新连接
- **THEN** 连接被放行，送达对应的内网主机

### Requirement: 其他协议仍用 masquerade
TCP、UDP、ICMP 以外的 IPv4 协议 SHALL 继续由内核的 masquerade 做地址转换。

#### Scenario: IPsec ESP 流量
- **WHEN** 一台 LAN 客户端建立使用 ESP 的 IPsec 隧道
- **THEN** ESP 报文以路由器的 WAN 地址发出，对端回送的 ESP 报文能送达这台客户端

### Requirement: einat 停止时回落到 masquerade
einat 停止运行时，TCP、UDP、ICMP 的地址转换 SHALL 自动回落到内核 masquerade，LAN 不断网。与此同时，按标记放行入站新连接的规则 SHALL 一并失效。

#### Scenario: 停止 einat
- **WHEN** 停止 einat 服务之后，LAN 客户端访问外部网络
- **THEN** 访问成功，转换改由 masquerade 完成，入站新连接不再被放行

### Requirement: 端口范围与本机端口隔离
einat 使用的公网端口范围 MUST NOT 与本机的临时端口范围重叠。路由器本机发起的连接 MUST NOT 被 einat 改写端口。

#### Scenario: 本机连接不被改写
- **WHEN** 路由器本机发起一条对外的 TCP 连接
- **THEN** 外部看到的源端口就是本机套接字的端口，没有被 einat 改写

### Requirement: 不转换 IPv6
einat MUST NOT 对 IPv6 做任何地址转换。

#### Scenario: LAN 通过 IPv6 访问外部
- **WHEN** 一台 LAN 客户端通过 IPv6 访问外部主机
- **THEN** 外部看到的源地址就是这台客户端自己的全局 IPv6 地址

### Requirement: 重拨后自动恢复
PPPoE 重拨、WAN 接口被重建或公网地址变化之后，einat SHALL 在 60 秒内重新挂载，恢复完全锥形行为。

#### Scenario: PPPoE 断开后重拨
- **WHEN** PPPoE 断开并重新拨号成功
- **THEN** 60 秒内新建立的连接重新表现为完全锥形 NAT

### Requirement: 注册健康检查
einat SHALL 向健康检查注册一个检查项：einat 进程在运行，并且当 WAN 接口存在时它已经挂在上面，这一项才通过。WAN 接口不存在（例如 PPPoE 还没拨上）MUST NOT 导致这一项失败。

#### Scenario: PPPoE 还没拨上
- **WHEN** einat 在运行但 pppoe-wan 接口还不存在时执行健康检查
- **THEN** einat 这一项判定为通过
