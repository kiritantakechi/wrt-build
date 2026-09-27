# Spec Delta

## Purpose

规定每周跟进上游 main 的节奏：机器人开 PR 更新 lock 文件，CI 构建出候选版，在设备的备用槽位上验证通过后才合并。

## ADDED Requirements

### Requirement: 每周自动开 PR
机器人 SHALL 每周检查一次 openwrt、packages、luci 的 main 分支。有更新时 SHALL 开一个 PR 更新 `upstream.lock`，PR 描述里列出新旧 SHA 和上游提交摘要。三个仓库都没有更新时 MUST NOT 开 PR。

#### Scenario: 上游有更新
- **WHEN** 到了每周检查的时间，并且上游有新的提交
- **THEN** 出现一个更新 `upstream.lock` 的 PR，描述里有新旧 SHA 和上游提交摘要

#### Scenario: 上游没有更新
- **WHEN** 到了每周检查的时间，但三个仓库都没有新提交
- **THEN** 不开 PR

### Requirement: 补丁打不上时明确失败
如果 bump 之后补丁无法应用，PR 的 CI SHALL 失败，并在结果中写明冲突的补丁文件名。

#### Scenario: BBRv3 补丁冲突
- **WHEN** bump 之后 BBRv3 的某个补丁打不上
- **THEN** PR 的检查失败，失败信息里写着冲突的补丁文件

### Requirement: 在设备上验证之后才合并
bump PR SHALL 带有一个必需的检查项：只有维护者记录了“候选版已在设备的备用槽位安装，并通过健康检查确认”之后，这个检查项才通过。这个检查项没有通过时，PR MUST NOT 被合并。

#### Scenario: 还没在设备上验证
- **WHEN** 候选版已经发布，但还没有记录设备上的验证结果
- **THEN** PR 不能合并

#### Scenario: 设备验证通过
- **WHEN** 维护者记录了验证结果：候选版已在备用槽位通过健康检查
- **THEN** 必需检查项通过，PR 可以合并
