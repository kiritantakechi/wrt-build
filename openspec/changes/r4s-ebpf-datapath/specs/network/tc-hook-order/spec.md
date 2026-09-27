# Spec Delta

## Purpose

规定同一网口上多个 eBPF/tc 程序的挂载顺序和返回值约束，以及各组件使用的报文 mark 位怎么分配，保证它们不会互相截断，也不会互相冲突。

## ADDED Requirements

### Requirement: WAN 口上的程序与顺序
在 WAN 接口的入方向和出方向上，einat SHALL 是最先执行的程序，其后才是 qosify 的分类器。除这两者外，其他组件 MUST NOT 在 WAN 接口上挂载 tc 或 tcx 程序。

#### Scenario: 检查 WAN 口
- **WHEN** 查看 pppoe-wan 上挂载的全部 BPF 程序
- **THEN** tcx 入口和出口上只有 einat，传统 tc 过滤器里只有 qosify 的分类器

### Requirement: 放行报文时必须让后续程序继续执行
挂在共享钩子上的程序放行报文时 MUST 返回“继续执行后续程序”，不能返回终止判定。只有在有意丢弃或重定向报文时例外。

#### Scenario: WAN 入站的 ICMP 回应
- **WHEN** 一台 LAN 主机 ping 外部地址，回应从 WAN 进入
- **THEN** 回应先经 einat 还原成内网地址，再被 qosify 分类（分类计数增加），最后送达这台主机

#### Scenario: 分片的 UDP 回应
- **WHEN** 一台 LAN 主机收到一个经 WAN 进入、被分片的 UDP 回应
- **THEN** 所有分片都被还原并送达，应用收到完整的数据

### Requirement: LAN 口上只有 dae
在 LAN 侧的受绑定接口上，dae SHALL 是唯一的 tc 或 tcx 程序。

#### Scenario: 检查 LAN 口
- **WHEN** 查看 br-lan 上挂载的全部 BPF 程序
- **THEN** 只有 dae 的程序

### Requirement: 顺序与启动先后无关
上述顺序 SHALL 在任何启动先后、任何组件重启、以及 PPPoE 重拨之后都保持成立。

#### Scenario: 重启组件之后
- **WHEN** 依次重启 qosify、einat、dae，再让 PPPoE 重拨一次
- **THEN** 每一步完成后，WAN 口和 LAN 口的程序和顺序仍满足上面的要求

### Requirement: mark 位统一分配
每个组件使用的报文 mark 位 SHALL 登记在仓库里的同一张分配表里，任意两个组件使用的位 MUST NOT 重叠。构建检查 SHALL 在配置中出现未登记或重叠的 mark 时失败。

#### Scenario: 配置了重叠的 mark
- **WHEN** 某个组件的配置使用了另一个组件已登记的 mark 位
- **THEN** 构建检查失败，并报出冲突的两个组件和对应的位
