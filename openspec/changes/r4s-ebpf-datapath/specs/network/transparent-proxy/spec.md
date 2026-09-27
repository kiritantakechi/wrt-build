# Spec Delta

## Purpose

用 dae 为局域网、容器和远程组网设备提供按规则分流的透明代理：直连流量完全留在内核里转发，路由器本机的流量不走代理。

## ADDED Requirements

### Requirement: 只绑定 LAN 侧接口
dae SHALL 只绑定 br-lan，以及存在时的 podman0 和 tailscale0。dae MUST NOT 在任何 WAN 接口上挂载程序，也 MUST NOT 挂载 cgroup 钩子。在 dae 启动之后才出现的受绑定接口，SHALL 在出现后 60 秒内完成绑定。

#### Scenario: 检查各接口上的程序
- **WHEN** dae 运行时，查看 br-lan 和 pppoe-wan 上挂载的 BPF 程序
- **THEN** br-lan 上有 dae 的程序，pppoe-wan 上没有任何 dae 的程序

#### Scenario: 容器网桥比 dae 晚出现
- **WHEN** dae 已经在运行，此时 podman0 才被创建
- **THEN** 60 秒内 podman0 上出现了 dae 的程序，容器流量开始按规则分流

### Requirement: 按规则分流
来自受绑定接口的流量 SHALL 按 dae 的规则分流：
- 直连流量 SHALL 由内核直接转发，不进入 dae 的用户态；
- 代理流量 SHALL 经由配置的代理节点发出。

#### Scenario: 访问直连目标
- **WHEN** 一台 LAN 客户端访问一个被规则判为直连的目标
- **THEN** 连接成功，目标看到的源地址是路由器的 WAN 地址，路由器上也看不到 dae 进程到这个目标的连接

#### Scenario: 访问代理目标
- **WHEN** 一台 LAN 客户端访问一个被规则判为走代理的目标
- **THEN** 连接成功，目标看到的源地址是代理节点的出口地址

### Requirement: 路由器本机流量直连
由路由器自身进程发起的流量 MUST NOT 经过 dae 代理。

#### Scenario: 路由器本机访问外部
- **WHEN** 在路由器上用命令行访问一个本来会被规则判为走代理的外部地址
- **THEN** 目标看到的源地址是路由器的 WAN 地址

### Requirement: 同时覆盖 IPv4 和 IPv6
分流 SHALL 同时作用于 LAN 的 IPv4 和 IPv6 流量。

#### Scenario: 通过 IPv6 访问代理目标
- **WHEN** 一台 LAN 客户端通过 IPv6 访问一个被规则判为走代理的目标
- **THEN** 流量经由代理节点发出

### Requirement: 配置管理
dae 的配置 SHALL 可以在 LuCI 里编辑，保存后热重载。完整配置（包括订阅和节点信息）MUST NOT 预置在固件镜像里，它的正本放在私有配置仓库。

#### Scenario: 在 LuCI 里保存配置
- **WHEN** 在 LuCI 里修改 dae 配置并保存
- **THEN** dae 热重载生效，重载期间直连流量不中断

#### Scenario: 检查镜像
- **WHEN** 检查固件镜像里的 dae 配置
- **THEN** 只有不含订阅和节点信息的模板

### Requirement: 停止时自动回落到直连
dae 停止运行或崩溃时，受绑定接口上的 dae 程序 SHALL 被移除，LAN 流量 SHALL 回落到内核直接转发。

#### Scenario: 停止 dae
- **WHEN** 停止 dae 服务
- **THEN** LAN 客户端仍然可以访问外部网络，所有流量都直连

### Requirement: 注册健康检查
dae SHALL 向健康检查注册一个检查项：只有当 dae 在运行，并且它的程序已经挂载到所有当前存在的受绑定接口上时，这一项才通过。

#### Scenario: dae 没有运行
- **WHEN** dae 进程没有运行时执行健康检查
- **THEN** dae 这一项判定为失败
