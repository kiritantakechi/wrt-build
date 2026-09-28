# Spec Delta

## Purpose

以 Prometheus 格式导出路由器的运行指标，只在 LAN 上暴露，供外部的监控系统采集。

## ADDED Requirements

### Requirement: 在 LAN 上导出指标
路由器 SHALL 在 LAN 地址的 9101 端口上以 Prometheus 文本格式提供指标，至少包括 CPU、内存、网络接口、文件系统和温度。这个端口 MUST NOT 能从 WAN 访问到。

#### Scenario: 从 LAN 采集
- **WHEN** 从一台 LAN 主机请求 `http://10.0.0.1:9101/metrics`
- **THEN** 返回 Prometheus 格式的指标，其中包含 CPU、内存、网络接口和文件系统

#### Scenario: 温度指标
- **WHEN** 在 R4S 上从 LAN 请求指标
- **THEN** 其中包含 SoC 的温度

#### Scenario: 从 WAN 访问
- **WHEN** 从 WAN 侧访问路由器的 9101 端口
- **THEN** 连接被拒绝

### Requirement: 不依赖数据盘
指标导出 SHALL 在数据盘不在时照常工作。

#### Scenario: 不接数据盘
- **WHEN** 不接数据盘时从 LAN 请求指标
- **THEN** 仍然能得到指标，其中也包含 SD 卡上文件系统的数据
