# Tasks

## 1. 信任锚与正式版构建

- [ ] 1.1 生成发布用的 apk EC 密钥对（prime256v1）和 usign 密钥对。私钥存进 GitHub `release-signing` environment 的 secrets，并给这个 environment 设置必需的审批人。验证：在 GitHub 的仓库设置里能看到这个 environment 和它的审批规则；仓库文件里没有任何私钥。
- [ ] 1.2 在自有 feed 里新增 `wrt-keyring`，安装 apk 公钥和 usign 公钥，支持多把。验证：解开生成的 apk，两类公钥都在预期路径。
- [ ] 1.3 新增 `config/release.seed`（`BUILDBOT`、去掉 `openwrt-keyring`、加入 `wrt-keyring`、不开 `SIGN_FIRMWARE`）。验证：用 release profile 构建出的镜像，`/etc/apk/keys` 里只有发布公钥，没有 `local-*` 或 `openwrt-*` 开头的公钥。
- [ ] 1.4 用 flake 构建签名工具 `.#sign-tools`（apk-tools v3、usign、ucert、fwtool，都用固定版本的源码）。验证：`nix run .#sign-tools -- --version` 能列出这四个工具的版本。

## 2. 签名与发布

- [ ] 2.1 编写 `sign` job：下载未签名的产物，按清单核对 sha256，用 `apk adbsign` 签索引，用 usign、ucert、fwtool 签镜像，最后用镜像里的发布公钥做一次校验。验证：审批之后产出签名后的产物，并通过校验；把某个产物改一个字节后重跑，job 在核对阶段失败；不审批时 job 一直停在等待状态。
- [ ] 2.2 核对权限隔离：检查构建 job 和签名 job 的定义。验证：只有 `sign` job 引用了 `release-signing` environment；构建 job 里读不到签名密钥（用一个打印 secrets 名称的调试步骤确认，然后删掉这个步骤）。
- [ ] 2.3 编写 `publish` job：核对运行标识；按 PR 构建和主分支构建分别发成 prerelease 或正式 release；上传各附件；从 lock 和补丁哈希生成说明。验证：人为混入另一次构建的产物时发布失败；正常情况下 Release 的附件齐全，说明里有三个 SHA 和补丁哈希。

## 3. 设备端同步与升级

- [ ] 3.1 在自有 feed 里实现 `wrt-sync`：一个 procd 服务加挂载触发器，在容器里下载、在宿主上校验，然后原子切换 `current`，只保留 3 个版本，支持 stable 和 candidate 两个通道；另附一个 Pod YAML 和每天执行的 cron。附带一组宿主侧逻辑的 shell 测试（用模拟文件覆盖校验失败、中途中断、清理旧版本三种情况）。验证：测试通过；上机临时阻断本机到 GitHub 的直连后，同步仍然成功。
- [ ] 3.2 覆盖 apk 的源列表，指向本地的 `current`。验证：WAN 断开时 `apk add` 一个本地仓库里的 kmod 能成功；拔掉数据盘时 apk 报告本地仓库不可用，路由功能正常。
- [ ] 3.3 实现 `wrt-update`，并在 `platform_check_image` 里强制校验签名。验证：用 `current` 里的升级镜像升级，成功进入非活动槽位并处于试运行状态；把镜像改一个字节或者去掉签名后升级，都被拒绝。
- [ ] 3.4 通道测试。验证：默认设置下只同步正式版；打开候选通道后才同步候选版。

## 4. 每周 bump

- [ ] 4.1 编写定时工作流：检查三个上游仓库，有更新就开 PR，PR 描述里写上新旧 SHA 和提交摘要；没有更新就不开。验证：手动触发一次，在上游有更新时开出 PR；把 lock 设成最新的 SHA 再触发一次，不开 PR。
- [ ] 4.2 设置分支保护，要求 `device-verified` 状态检查；实现 `just verify-pr <n>`，用 `gh api` 写入这个状态。验证：写入状态之前 PR 不能合并，写入之后可以合并。
- [ ] 4.3 编写 `docs/release-flow.md`：完整说明 bump PR → 候选版 → 设备上 `wrt-sync --candidate` → `wrt-update` → 健康检查确认 → `just verify-pr` → 合并的流程。验证：完整走一遍真实的 bump，每一步都有记录。

## 5. 配置推送

- [ ] 5.1 建立私有仓库 `wrt-config` 的骨架（`.sops.yaml`、`secrets`、`dae`、`pods`、`uci` 模板），并生成 age 密钥。验证：用 gitleaks 扫描仓库的全部历史，没有发现明文密钥；离线备份 age 密钥的方法写进 `docs/ops.md`。
- [ ] 5.2 实现 `just push <host>`：解密、渲染模板、本机校验、在设备上预校验 dae 配置、按哈希只重载有变化的服务、失败时回滚、只用 SSH 密钥认证。附带一组用模拟 SSH 目标驱动的测试。验证：测试覆盖以下五种情况，全部通过——语法错误在改动设备前就中止；重复推送不重启服务；重载失败会恢复原配置并以非零退出；用户配置里写了 `lan_interface` 会被拒绝；没有 SSH 密钥时直接失败，不会退回去用密码登录。
- [ ] 5.3 把推送写入的路径追加到镜像的 `/etc/sysupgrade.conf`。验证：推送之后做一次保留配置的 A/B 升级，新槽位里 PPPoE、dae、WireGuard、Tailscale 和 SMB 的配置都在。

## 6. 端到端演练

- [ ] 6.1 从零开始完整走一遍：生成密钥 → 第一次正式发布 → 刷写出厂镜像 → 推送配置 → 同步 → 下一次正式发布 → `wrt-update` → 健康检查确认。验证：每一步的结果记录在 `docs/validation/release.md`，最终设备运行在新版本上并已确认。
