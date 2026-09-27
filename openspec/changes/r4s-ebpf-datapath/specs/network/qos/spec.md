# Spec Delta

## Purpose

在 PPPoE 出口的上行方向用 cake 做整形，并按 DSCP 分类；下行不做整形，以保留 flowtable 的转发加速。

## ADDED Requirements

### Requirement: 只整形上行
pppoe-wan 的出方向 SHALL 由 cake 按配置的上行带宽整形，并补偿 PPPoE 的封装开销。入方向 MUST NOT 整形，系统里 MUST NOT 存在 ifb 设备。

#### Scenario: 检查队列规则
- **WHEN** 查看 pppoe-wan 的队列规则和系统里的网络设备
- **THEN** pppoe-wan 的根队列是按配置带宽运行的 cake，系统里没有 ifb 设备

### Requirement: 按内网主机公平分配
即使地址转换是由 einat 完成的，cake SHALL 仍能在各台 LAN 主机之间公平分配上行带宽。

#### Scenario: 两台主机同时满速上传
- **WHEN** 两台 LAN 主机同时以尽可能高的速率上传，持续 60 秒
- **THEN** 两者的平均上行速率之差不超过 20%

### Requirement: 按 DSCP 分类
qosify SHALL 按规则（端口、DNS 名称、大流量检测）把出方向流量分进 diffserv4 的各个档位。

#### Scenario: 分类到语音档
- **WHEN** 一条流量命中了被设为 voice 类的规则
- **THEN** cake 的统计显示这条流量进入了语音档位

### Requirement: 重拨后恢复
PPPoE 重拨或 WAN 接口被重建后，整形和分类 SHALL 在 60 秒内恢复。

#### Scenario: PPPoE 重拨
- **WHEN** PPPoE 断开后重新拨号成功
- **THEN** 60 秒内 pppoe-wan 上重新出现 cake 和 qosify 的分类器
