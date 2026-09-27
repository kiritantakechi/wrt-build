# Proposal

## Why

这条发布流程要解决五个问题：

- **签名和分发必须自己做。** 内核是自编的，kmod 和固件都只能由本项目签名、分发。
- **从 GitHub 直接拉更新不可靠。** dae 只绑 LAN，路由器本机流量走直连，在国内直接从 GitHub 拉更新不稳定。
- **签名密钥不能碰第三方代码。** 构建时会执行大量第三方 Go 和 Rust 代码，签名密钥不能出现在执行这些代码的 job 里。
- **跟进上游需要可控的节奏。** 每周跟进 main，需要一个风险低的“验证后再合并”流程。
- **运行时密钥不能公开。** PPPoE 账号、dae 订阅、WireGuard 私钥、Tailscale 认证这些东西，不能出现在公开仓库或镜像里。

## What Changes

- **签名**
  - CI 里设一个独立的签名 job，只对构建产物签名，不执行任何第三方代码。
  - apk 仓库和固件的签名密钥放在 GitHub 的受保护环境（environment）里，每次签名都需要人工审批。
  - 签名工具（apk-tools、usign、ucert、fwtool）由 Nix 用固定版本的源码单独构建，不用构建 job 产出的二进制。
  - 正式版仿照官方做法：打开 `CONFIG_BUILDBOT`，让构建时临时生成的密钥不进镜像；再由自有的 `wrt-keyring` 包提供发布公钥，并且不带 OpenWrt 官方的公钥。
- **发布**：签名后的单槽升级镜像、出厂镜像，以及含全部 kmod 的 apk 仓库，一起发布到 GitHub Releases。
- **设备端同步**
  - 路由器上跑一个容器，它的流量经 podman0 走 dae 代理，负责把 Release 产物同步到 `/mnt/data/repo`。
  - apk 从这个本地仓库装包，sysupgrade 也从本地文件写入非活动槽位。
  - 签名公钥预置在镜像里。
  - 数据盘不在时，只是不能装包和升级，已经装好的系统照常运行。
- **每周跟进上游**
  - 机器人每周更新一次 `upstream.lock` 并开 PR。
  - CI 构建完成后刷到备用槽位验证，通过了才合并。
  - 如果 BBRv3 等补丁打不上，CI 立即失败。
- **配置推送**
  - 私有配置仓库保存密钥和运行时配置，包括 config.dae。密钥用 sops + age 加密后再提交，只在工作站上解密。
  - 推送脚本经 SSH 写入路由器，并触发对应服务重载。
  - 公开仓库和镜像里都不出现任何密钥。

## Capabilities

### New Capabilities

- `release/signing`：签名 job 的隔离方式、密钥存放位置和审批流程。
- `release/publishing`：发布哪些产物、发布到哪里，以及产物的组织方式。
- `release/device-sync`：设备端经代理把产物同步到本地仓库，以及 apk 和 sysupgrade 如何使用本地产物。
- `release/upstream-bump`：每周更新 lock 文件的 PR、验证后合并的节奏，以及补丁打不上时的处理。
- `ops/config-push`：私有配置仓库，以及密钥与运行时配置的推送和生效方式。

### Modified Capabilities

（无。）

## Impact

- **GitHub**：Actions、受保护环境（environment）、Releases、定时工作流和开 PR 的机器人。
- **新增**：私有配置仓库，以及对应的推送工具（`just` 命令）。
- **设备端**：同步容器、本地 apk 仓库的配置、预置的签名公钥。
- **依赖其他 change**：
  - `r4s-build-foundation`：CI 和构建产物。
  - `r4s-ab-rollback`：写入备用槽位和回滚。
  - `r4s-services`：数据盘和 podman。
  - `r4s-ebpf-datapath`：容器流量经 dae 代理。
