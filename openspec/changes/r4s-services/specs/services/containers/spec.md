# Spec Delta

## Purpose

规定容器运行时的存储位置、网络与防火墙的分工、容器流量和透明代理的关系，以及以声明方式定义的应用容器怎样开机自动启动。

## ADDED Requirements

### Requirement: 容器存储放在数据盘
容器镜像和容器数据 SHALL 全部存放在 `@containers` 上。SD 卡 MUST NOT 保存任何容器镜像层或容器数据。

#### Scenario: 拉取一个镜像
- **WHEN** 拉取一个容器镜像
- **THEN** 镜像层写在 `@containers` 上，overlay 分区的使用量没有增加

### Requirement: 单一防火墙和单一 NAT
容器运行时 MUST NOT 自己安装防火墙或 NAT 规则。容器网桥 SHALL 属于 fw4 中一个独立的区域，容器出网的地址转换 SHALL 与 LAN 一样由 einat 完成（einat 不可用时回落到 masquerade）。需要对外开放容器端口时，SHALL 通过 fw4 的端口转发规则实现。

#### Scenario: 检查规则集
- **WHEN** 运行一个桥接网络的容器后查看 nftables 规则集
- **THEN** 其中没有容器运行时自己创建的表，只有 fw4 和各数据面组件的规则

#### Scenario: 容器访问外网
- **WHEN** 一个桥接网络的容器访问外网
- **THEN** 访问成功，外部看到的源地址是路由器的 WAN 地址

#### Scenario: 对外开放容器端口
- **WHEN** 在 fw4 里为容器配置一条 WAN 端口转发，端口不在 einat 的端口范围内
- **THEN** 外部可以访问到这个容器端口

### Requirement: 容器流量走透明代理
容器网桥上的流量 SHALL 与 LAN 一样由 dae 按规则分流。

#### Scenario: 容器访问代理目标
- **WHEN** 一个容器访问一个被规则判为走代理的目标
- **THEN** 流量经由代理节点发出

### Requirement: 声明式定义与开机自动启动
应用容器 SHALL 用放在数据盘上的声明文件来定义。数据盘挂载完成后，系统 SHALL 按这些声明文件自动启动对应容器，而且重复执行时结果一致（声明未变就不重建）。

#### Scenario: 开机自动启动
- **WHEN** 数据盘上有一个应用容器（例如 qBittorrent）的声明文件，系统重启
- **THEN** 数据盘挂载完成后，这个容器自动运行起来

#### Scenario: 声明未改变
- **WHEN** 声明文件没有变化，再触发一次启动流程
- **THEN** 已经在运行的容器没有被重建

### Requirement: 应用容器放在固件之外
qBittorrent 这类应用 SHALL 以容器方式运行，固件镜像 MUST NOT 包含它们的原生软件包。

#### Scenario: 检查镜像
- **WHEN** 列出固件镜像里的软件包
- **THEN** 其中没有 qBittorrent、Qt 或 libtorrent
