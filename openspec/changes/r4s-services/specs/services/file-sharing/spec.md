# Spec Delta

## Purpose

规定内核 SMB 服务（ksmbd）的暴露范围、共享目录和访问控制，在尽量省内存的前提下，为局域网提供文件共享。

## ADDED Requirements

### Requirement: 只在 LAN 提供
SMB 服务 SHALL 只在 LAN 接口上提供。从 WAN、WireGuard 和 Tailscale 都 MUST NOT 能访问到。

#### Scenario: 从 LAN 访问
- **WHEN** 从一台 LAN 客户端连接 `smb://10.0.0.1`
- **THEN** 能看到共享列表

#### Scenario: 从 WAN 或 VPN 访问
- **WHEN** 分别从 WAN 侧、一台 WireGuard 设备、一台 tailnet 设备连接路由器的 445 端口
- **THEN** 三种情况下连接都被拒绝

### Requirement: 共享目录位于数据盘
所有共享 SHALL 指向 `@shares` 下面的目录。数据盘不在时，SMB 服务 MUST NOT 提供任何共享。

#### Scenario: 数据盘不在
- **WHEN** 不接数据盘时启动系统
- **THEN** SMB 服务没有运行，也没有任何共享可以访问

### Requirement: 需要认证
访问共享 SHALL 需要用户名和密码，MUST NOT 允许匿名访问。共享用户的凭据 MUST NOT 预置在镜像里。

#### Scenario: 匿名访问
- **WHEN** 客户端尝试以匿名方式连接共享
- **THEN** 连接被拒绝

### Requirement: 协议版本
SMB 服务 SHALL 只提供 SMB 3 协议，MUST NOT 接受 SMB 1。

#### Scenario: 用 SMB 1 客户端连接
- **WHEN** 一个只支持 SMB 1 的客户端尝试连接
- **THEN** 协商失败
