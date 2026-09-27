# Spec Delta

## Purpose

规定升级只写入当前没在运行的槽位，并把配置带到新槽位；升级过程中出任何意外，都不会影响正在运行的系统。

## ADDED Requirements

### Requirement: 只写入非活动槽位
升级 SHALL 只写入非活动槽位的 boot 分区和 root 分区。升级 MUST NOT 修改当前活动槽位、U-Boot 区域或分区表。

#### Scenario: 从槽位 A 升级
- **WHEN** 在槽位 A 上运行时执行升级
- **THEN** 只有 boot-B 和 root-B 的内容发生变化，boot-A、root-A 和引导区域的校验和与升级前相同

#### Scenario: 升级写到一半断电
- **WHEN** 写入非活动槽位的过程中断电
- **THEN** 重新上电后设备仍然从原来的槽位正常启动

### Requirement: 新槽位从全新的 overlay 开始
写入新系统之后，非活动槽位原有的 overlay SHALL 作废，新系统第一次启动时 SHALL 建立一个全新的 overlay，只包含迁移过来的配置。

#### Scenario: 旧 overlay 中的残留文件
- **WHEN** 槽位 B 原有的 overlay 里有一个用户文件，然后执行升级并进入槽位 B
- **THEN** 新系统里这个文件不存在

### Requirement: 配置迁移
默认保留配置时，当前系统的配置备份 SHALL 被放到新槽位首次启动时能读到的位置，并在首次启动时恢复。选择不保留配置时，新槽位 SHALL 以出厂默认配置启动。

#### Scenario: 保留配置升级
- **WHEN** 用默认方式升级并进入新槽位
- **THEN** 新系统的配置和升级前一致

#### Scenario: 不保留配置升级
- **WHEN** 指定不保留配置进行升级
- **THEN** 新槽位以出厂默认配置启动

### Requirement: 写入完成后进入试运行
写入成功后，升级 SHALL 把 `boot_slot` 指向新槽位，设置 `upgrade_available` 为 1、`bootcount` 为 0，然后重启。只有健康检查确认之后，新槽位才 SHALL 成为长期使用的槽位。

#### Scenario: 升级完成后重启
- **WHEN** 升级写入完成
- **THEN** 设备重启进入新槽位，并处于试运行状态

### Requirement: 拒绝不匹配的镜像
升级 MUST 拒绝元数据与本设备不匹配的镜像，也 MUST 拒绝格式不是单槽升级镜像的文件。

#### Scenario: 其他设备的镜像
- **WHEN** 用一个为其他设备构建的镜像执行升级
- **THEN** 升级被拒绝，两个槽位都没有被写入

### Requirement: 手动切换槽位
管理员 SHALL 能手动切换到另一个槽位，例如退回上一个版本。切换后以试运行状态启动那个槽位。

#### Scenario: 手动退回上一版本
- **WHEN** 管理员在槽位 B 上执行切换命令
- **THEN** 设备重启进入槽位 A，并处于试运行状态，通过健康检查后被确认
