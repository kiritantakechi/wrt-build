# Spec Delta

## Purpose

规定局域网的 DNS 链路：dnsmasq 负责 DHCP 和本地主机名，外部域名的查询交给 dae，由 dae 完成按域名分流所需的解析。

## ADDED Requirements

### Requirement: dnsmasq 仍是 LAN 的 DNS 服务器
DHCP SHALL 把路由器的 LAN 地址作为 DNS 服务器下发给客户端。本地主机名（`.lan`）的查询 SHALL 由 dnsmasq 自己回答。

#### Scenario: 查询本地主机名
- **WHEN** 一台 LAN 客户端查询另一台客户端的 `<主机名>.lan`
- **THEN** 得到对方的 LAN 地址，这次查询不经过 dae

### Requirement: 外部域名交给 dae 解析
dnsmasq SHALL 把所有非本地的查询转发给 dae 在回环地址上的 DNS 监听端口，由 dae 按它的上游规则解析。

#### Scenario: 查询外部域名
- **WHEN** 一台 LAN 客户端查询一个外部域名
- **THEN** 查询被转发到 dae，dae 的日志里有这条查询记录，客户端得到解析结果

### Requirement: dae 不可用时回落到上游 DNS
当 dae 的 DNS 监听不可用时，dnsmasq SHALL 改用 WAN 上获得的上游 DNS 继续解析，不能让 LAN 断网。

#### Scenario: 停止 dae 后解析
- **WHEN** 停止 dae 之后，LAN 客户端查询一个外部域名
- **THEN** 仍然能得到解析结果

### Requirement: dae 的 DNS 端口不对外暴露
dae 的 DNS 监听 MUST 只绑定在回环地址上，从 LAN 或 WAN 都 MUST NOT 能访问到它。

#### Scenario: 从 LAN 访问 dae 的 DNS 端口
- **WHEN** 从一台 LAN 客户端向路由器 LAN 地址上的 dae DNS 端口发送查询
- **THEN** 查询得不到响应
