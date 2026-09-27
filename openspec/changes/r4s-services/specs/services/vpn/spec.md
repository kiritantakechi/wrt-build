# Spec Delta

## Purpose

规定 WireGuard 和 Tailscale 两种组网方式各自的角色、在防火墙中的归属，以及和透明代理的关系。

## ADDED Requirements

### Requirement: WireGuard 远程接入
固件 SHALL 提供内核 WireGuard，用于远程设备回家访问 LAN。WireGuard 的私钥和对端配置 MUST NOT 预置在镜像里。

#### Scenario: 远程设备接入
- **WHEN** 一台已配置好的远程设备通过 WireGuard 连接路由器
- **THEN** 它可以访问 LAN 上的主机，但访问不到路由器上只对 LAN 开放的服务（例如 SMB）

### Requirement: Tailscale 组网
固件 SHALL 提供 Tailscale，并能把 LAN 网段宣告为子网路由。Tailscale 的防火墙规则 SHALL 使用 nftables。认证凭据 MUST NOT 预置在镜像里。

#### Scenario: 通过子网路由访问 LAN
- **WHEN** tailnet 里的另一台设备访问 LAN 上的一台主机
- **THEN** 经由这台路由器的子网路由访问成功

### Requirement: 与透明代理的关系
经 Tailscale 进入的流量 SHALL 与 LAN 流量一样由 dae 按规则分流。经 WireGuard 进入的流量 SHALL 直连，不经过代理。

#### Scenario: tailnet 设备访问代理目标
- **WHEN** 一台 tailnet 设备把这台路由器当作出口，访问一个被规则判为走代理的目标
- **THEN** 流量经由代理节点发出

#### Scenario: WireGuard 设备访问外网
- **WHEN** 一台 WireGuard 设备通过路由器访问外网
- **THEN** 外部看到的源地址是路由器的 WAN 地址

### Requirement: mark 位登记
Tailscale 使用的报文 mark 位 SHALL 登记进 mark 分配表，并且 MUST NOT 与其他组件重叠。

#### Scenario: 检查分配表
- **WHEN** 运行 mark 检查
- **THEN** 分配表里有 Tailscale 的条目，并且检查通过
