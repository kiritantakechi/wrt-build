# Tasks

## 1. 信任锚与构建形态

- [ ] 1.1 生成发布用的 apk EC 密钥对（prime256v1）和 usign 密钥对。私钥存进 GitHub `release-signing` environment 的 secrets，并给这个 environment 设置必需的审批人。验证：`scripts/github-audit.sh` 读出这个 environment 和它的审批规则；仓库文件里没有任何私钥（`just check` 里的 gitleaks 扫描通过）。
- [ ] 1.2 在自有 feed 里新增 `wrt-keyring`，安装 apk 公钥和 usign 公钥，支持多把。验证：`test_signing.py` 的“检查镜像中的信任锚”用例读取镜像审计的输出，只看到这些公钥。
- [ ] 1.3 在 `config/ci.seed` 里加入 `BUILDBOT`、去掉 `openwrt-keyring`、加入 `wrt-keyring`、不开 `SIGN_FIRMWARE`（design D1）。验证：CI 构建出的镜像里 `/etc/apk/keys` 只有发布公钥，没有 `local-*` 或 `openwrt-*` 开头的公钥。
- [ ] 1.4 用 flake 构建签名工具 `.#sign-tools`（apk-tools v3、usign、ucert、fwtool，都用固定版本的源码）。验证：`nix run .#sign-tools -- --version` 能列出这四个工具的版本。
- [ ] 1.5 在 `wrt_tests/keys.py` 实现临时密钥，以及 `signed_repo` 和 `trust` 两个夹具；把 foundation 里安装 kmod 的用例改为使用 `signed_repo`。验证：`tests/unit/test_keys.py` 用生成的密钥签名、验签一次；`firmware/test_kernel.py` 在 ci 构建上仍然通过。

## 2. 签名与发布

- [ ] 2.1 实现 `scripts/release-sign.sh`：核对清单中的 sha256，用 `apk adbsign` 签索引，用 usign、ucert、fwtool 签镜像，用传入的公钥做一次校验，写出 `SHA256SUMS`。验证：`tests/release/test_signing.py` 用临时密钥覆盖“产物与清单不一致”“签名后的软件包索引”“轮换过渡期”三个场景。
- [ ] 2.2 编写 `sign` job，只引用 `release-signing` environment，步骤只有下载产物、`nix run .#sign-tools` 和 `release-sign.sh`。验证：`test_signing.py` 中的工作流审计用例覆盖“检查构建 job 的权限”和“检查签名 job 执行的内容”；“没有批准”的场景由 GitHub 的 environment 保护保证，登记在 `verified-elsewhere.toml` 里，由 `github-audit.sh` 核对。
- [ ] 2.3 实现 `scripts/release-publish.sh`：核对运行标识，组装附件和 `release.json`（tag、是否预发布、说明文字），最后调用 `gh release create`。编写 `publish` job，排在 `upgrade-drill` 之后。验证：`tests/release/test_publishing.py` 覆盖 publishing 规格的全部场景（上传步骤以组装结果为准，不真的调用 GitHub）。
- [ ] 2.4 实现 `scripts/github-audit.sh`，核对 environment 的审批人和分支保护的必需检查项（包括 `upgrade-drill`），加进 check 工作流的定时任务。验证：在本仓库上运行，输出与预期一致；在一个故意缺少审批人的测试仓库上运行时失败。

## 3. 设备端同步与升级

- [ ] 3.1 在自有 feed 里实现 `wrt-sync`：一个 procd 服务加挂载触发器，在容器里下载、在宿主上校验，然后原子切换 `current`，只保留 3 个版本，支持 stable 和 candidate 两个通道，Releases 的地址可配置；另附一个 Pod YAML 和每天执行的 cron。验证：由 `test_device_sync.py` 中关于同步的各个场景覆盖。
- [ ] 3.2 覆盖 apk 的源列表，指向本地的 `current`。验证：由“WAN 断开时安装 kmod”和“不接数据盘”两个用例覆盖。
- [ ] 3.3 实现 `wrt-update`，并在 `platform_check_image` 里强制校验签名。验证：由“镜像被篡改”的用例覆盖；另有一条用例确认没有签名的镜像同样被拒绝。
- [ ] 3.4 在 `wrt_tests/` 里实现模拟的 GitHub Releases API：放在 `inet` 里，用测试 CA 签发的证书提供 HTTPS，数据来自一个目录下的 `release.json` 和附件；支持中途断开连接，用来测试被打断的同步。验证：`tests/unit/test_releases.py` 用 curl 访问它，列表、下载和断开都符合预期。

## 4. 每周 bump 与升级演练

- [ ] 4.1 实现 `scripts/upstream-bump.sh` 和定时工作流：检查三个上游仓库，有更新就开 PR，PR 描述里写上新旧 SHA 和提交摘要；没有更新就不开。验证：`tests/release/test_upstream_bump.py` 用本地裸仓库充当上游，覆盖“上游有更新”和“上游没有更新”两个场景（开 PR 那一步只检查生成的标题和描述）；补丁冲突的场景用一个与补丁冲突的假上游驱动 `patch.sh`，确认失败信息里有补丁文件名。
- [ ] 4.2 编写 `upgrade-drill` job 和 `-m drill` 用例：拿到最新正式版的出厂镜像（还没有正式版时，用本次构建的出厂镜像），推送测试配置，同步候选版，执行 `wrt-update`，然后等待健康检查确认。`system-test` 用临时密钥跑同一组用例。验证：“演练通过”在 `system-test` 中通过；“候选版通不过健康检查”的用例在保留的配置里放一个一定失败的检查项，确认设备回到原槽位、用例判定演练失败。
- [ ] 4.3 设置分支保护，把 `upgrade-drill` 设为必需检查项。验证：`github-audit.sh` 能核对到这一项；一个演练失败的 PR 不能合并。
- [ ] 4.4 编写 `docs/release-flow.md`：bump PR → 签名审批 → 升级演练 → 候选版发布 → 合并 → 主分支签名审批 → 演练 → 正式版发布 → 设备同步和 `wrt-update`。验证：第一次真实的 bump 按文档走完，每一步的链接记录在 `docs/validation/release.md`。

## 5. 配置推送

- [ ] 5.1 实现 `scripts/config-init.sh`（对应 `just config-init`），生成私有仓库 `wrt-config` 的骨架（`.sops.yaml`、`secrets`、`dae`、`pods`、`uci` 模板），并生成 age 密钥；`sops`、`age` 加进 flake 的两种 devShell。验证：`test_config_push.py` 对生成的骨架和一个填好测试密钥的夹具仓库运行 gitleaks，全部历史里都找不到明文密钥；离线备份 age 密钥的方法写进 `docs/ops.md`。
- [ ] 5.2 实现 `scripts/config-push.sh`（对应 `just config-push <host>`）：解密、渲染模板、本机校验、在设备上预校验 dae 配置、按哈希只重载有变化的服务、失败时回滚、只用 SSH 密钥认证。验证：`tests/ops/test_config_push.py` 对模拟器里的路由器推送，覆盖 config-push 规格中除“升级到另一个槽位”以外的全部场景。
- [ ] 5.3 把推送写入的路径追加到镜像的 `/etc/sysupgrade.conf`。验证：由“升级到另一个槽位”的用例覆盖（推送后做一次保留配置的 A/B 升级）。

## 6. 模拟器与宿主用例汇总

- [ ] 6.1 `tests/release/test_device_sync.py`：覆盖 device-sync 规格的全部场景。其中“本机无法直连”由 `isp` 阻断路由器 WAN 地址到模拟 Releases 服务的流量；“同步中途被打断”由模拟服务断开连接；“保留最近的版本”连续发布 4 个版本。验证：用例全部通过。
- [ ] 6.2 运行 `spec-coverage`。验证：这个 change 没有未覆盖的场景，只有“没有批准”一项登记在 `verified-elsewhere.toml`。

## 7. 首次上线

- [ ] 7.1 按 design 的 Migration Plan 生成正式密钥、完成第一次正式发布、在真机上刷写出厂镜像并推送配置，然后运行 `just test-device <host>`。验证：报告全部通过，结果存档到 `docs/validation/release.md`；设备上 `wrt-sync` 能同步到这次发布。
