# Design

## Context

动机见 proposal.md。以下现状都在上游源码里核对过（OpenWrt main `1019293`）：

- **apk 索引的签名方式**：索引由 `apk mkndx --sign $(BUILD_KEY_APK_SEC)` 签名（`package/Makefile:86-95,195-200`）。私钥是 `$(TOPDIR)/private-key.pem`，文件不存在时会自动生成一把 prime256v1 密钥；公钥由私钥导出（`package/Makefile:77-81`，`rules.mk:350-351`）。
- **构建密钥会被装进镜像**：base-files 在 `CONFIG_BUILDBOT` 没开时，会把构建公钥装进镜像的 `/etc/apk/keys/`（`package/base-files/Makefile:124-128`）。
- **官方构建的做法**：打开 `CONFIG_BUILDBOT`，再用 `openwrt-keyring` 包提供发布公钥（`package/system/openwrt-keyring/Makefile:33-37`）。
- **`CONFIG_BUILDBOT` 的其他副作用**：
  - 在 `PER_FEED_REPO` 模式下，生成的软件源列表里会多出一条 kmods 路径（`include/feeds.mk:40-56`）。本设计会整个覆盖这份列表，所以没有影响。
  - 工具链目录的 git 版本变化时会强制清空重建（`toolchain/Makefile:65-75`）。这与 foundation 设计里按工具链输入决定缓存的做法一致。
- **固件签名**：`CONFIG_SIGN_FIRMWARE` 用 usign/ucert 给固件的元数据签名（`include/image-commands.mk:94,125`）。rockchip 的 `platform.sh` 要求固件带元数据（`REQUIRE_IMAGE_METADATA=1`）。
- **上游 change 提供的前提**：
  - `r4s-build-foundation` 产出未签名的产物和 `manifest.json`；
  - `r4s-ab-rollback` 提供写非活动槽位和 `wrt-slot`；
  - `r4s-services` 提供数据盘、podman 和声明式 Pod；
  - `r4s-ebpf-datapath` 让容器流量经过 dae；
  - foundation 的模拟环境和测试框架，以及后续 change 补齐的运营商、互联网和数据盘。

## Goals / Non-Goals

**Goals:**
- 即使构建 job 被攻破，攻击者也拿不到能长期冒充发布者的密钥。
- 设备端的更新完全不依赖路由器本机直连 GitHub。
- 每周 bump 有一道验证闸门：从上一个正式版升级到候选版的完整过程，在 CI 的模拟器里自动演练，不需要真机。人工只负责批准签名和点合并。
- 签名、发布、同步、推送的逻辑都在模拟器或宿主上有自动用例；CI 和测试调用的是同一份脚本，只是用的密钥不同。

**Non-Goals:**
- 在构建 job 被攻破的情况下，保证当次构建产物本身的完整性。这需要可复现构建加上第三方重建比对，不在本 change 范围内。
- 自建软件源服务器或 CDN。
- 多台设备的批量管理。

## Decisions

### D1. 两种构建形态和信任锚

- **CI 构建就是发布构建**：`config/ci.seed` 增加下面几项，不再单独设 release profile。于是 CI 构建的、模拟器测试的、签名发布的，始终是同一份镜像。两个 profile 形成对称：`dev` 信任本地构建密钥，`ci` 信任发布公钥。

```
CONFIG_BUILDBOT=y
# CONFIG_PACKAGE_openwrt-keyring is not set
CONFIG_PACKAGE_wrt-keyring=y
# CONFIG_SIGN_FIRMWARE is not set
```

- **`wrt-keyring` 包**：放在自有 feed 里，安装 `/etc/apk/keys/wrt-release-<id>.pem`（apk 用的 EC 公钥）和 usign 公钥。支持同时放多把，用于轮换。
- **构建过程中的签名**：构建时仍然会生成一把一次性的 apk 私钥，给构建内部的安装和建索引用。因为打开了 `BUILDBOT`，这把钥匙的公钥不会进镜像。构建时也不给固件签名。
- **开发版**：dev profile 不开 `BUILDBOT`，沿用上游行为，镜像信任本地构建的密钥。这类镜像只用于调试，不会发布。
- **对已有用例的影响**：foundation 里“安装同一次构建的 kmod”那条用例，改为使用 `signed_repo` 夹具。这个夹具用临时密钥把本次构建的仓库重新签名，并把临时公钥写进测试 overlay（见 D7）。
- **备选方案**：
  - 给 base-files 打补丁，跳过安装构建公钥。否决，因为上游已经有 `BUILDBOT` 这条现成的路径。
  - 单独设一个 release profile。否决，因为那样 CI 测试的镜像和发布的镜像就不是同一份了。

### D2. 签名 job

```
job sign  (needs: firmware; environment: release-signing -> required reviewer)
  1. download unsigned artifacts + manifest.json from the firmware job
  2. verify every artifact's sha256 against manifest.json  (mismatch -> abort)
  3. nix run .#sign-tools   (apk-tools v3, usign, ucert, fwtool built by Nix from
                             pinned first-party sources; no package build, no feeds)
  4. scripts/release-sign.sh <in> <out> --apk-key $APK_KEY --fw-key $FW_KEY
       apk adbsign every packages.adb; usign + ucert + fwtool on factory image and upgrade tar;
       verify the result against the public keys shipped in wrt-keyring; write SHA256SUMS
  5. upload signed set for upgrade-drill and publish
```

- **签名工具的来源**：签名工具由 flake 用固定版本的源码自行构建，不使用构建 job 产出的宿主工具。那些工具出自可能被攻破的 job，拿来签名就等于绕开了隔离。
- **同一份签名脚本**：`release-sign.sh` 只接收输入目录、输出目录和两把密钥。CI 传入正式密钥；测试传入临时密钥，覆盖篡改、轮换和信任锚这些场景。
- **密钥存放**：两把私钥存为 `release-signing` 这个 environment 的 secrets，只有这个 environment 能读到。这个 environment 设置了必需的审批人，满足“每次签名都需要人工审批”。
- **备选方案**：
  - 在本机签名。探索阶段已经决定不用。
  - 在构建 job 里签名。否决，理由见 proposal。

### D3. 发布

`publish` job 在 `upgrade-drill` 通过之后执行（D5）。发布内容由 `scripts/release-publish.sh` 先组装成一个目录和一份 `release.json`（tag、是否预发布、说明文字、附件列表），最后一步才用 `gh release create` 上传。组装部分由宿主用例覆盖。

- **一致性校验**：先核对 `manifest.json` 里的运行标识与全部产物一致，不一致就中止。
- **Release 命名**：tag 为 `r<YYYYMMDD>-<openwrt短SHA>-<运行号>`；PR 构建发为 prerelease，主分支构建发为正式 release。
- **附件**：出厂镜像、升级 tar、`repo.tar.zst`（按 apk 的仓库目录结构组织，包括 targets 和 packages）、`manifest.json`、`SHA256SUMS`。
- **说明文字**：由 `upstream.lock` 和补丁队列的哈希自动生成。
- **体积上限**：单个附件最大 2 GB，仓库归档预计在几百 MB 左右。

### D4. 设备端同步

```
wrt-sync (procd service, mount trigger /mnt/data)
  -> podman kube play pods/wrt-sync.yaml   (image: minimal curl+jq, network: podman bridge
                                             -> proxied by dae)
       container: query GitHub Releases API (channel: stable | candidate)
                  download assets into /mnt/data/repo/.incoming/<tag>/
  -> host side (after container exits 0):
       verify sha256 against manifest.json  AND  apk index signature with /etc/apk/keys
       mv .incoming/<tag> -> releases/<tag>; ln -sfn releases/<tag> current
       keep newest 3, delete older
cron: daily
```

- **Releases 的地址可配置**：UCI 选项 `wrt-sync.main.api` 默认是 `https://api.github.com`，测试把它指向沙箱里的模拟服务。
- **容器不需要被信任**：完整性由宿主这边用镜像里的发布公钥校验。所以同步容器可以用第三方的最小镜像，它只负责下载。
- **原子切换**：新版本先下载到 `.incoming`，全部校验通过后才改 `current` 这个符号链接。
- **apk 源列表**：`/etc/apk/repositories.d/distfeeds.list` 被覆盖，改为指向 `current` 下的本地仓库，路径是 `file` 形式的 `packages.adb`。
- **本地升级**：`wrt-update` 调用 sysupgrade 升级到 `current` 里的升级 tar。
- **签名强制检查**：`platform_check_image`（来自 A/B 那个 change）额外要求镜像必须带有效签名。在 `REQUIRE_IMAGE_METADATA` 的基础上，用 ucert 对照镜像里的公钥校验。

### D5. 每周 bump

- **定时工作流**：每周一执行，读取三个上游仓库 main 的 HEAD。有变化就更新 `upstream.lock`，用 GitHub App 或默认的 token 开 PR。PR 描述里写入新旧 SHA，以及 `git log --oneline` 的摘要，最多 50 行。
- **PR 的检查**：foundation 的 CI 会在补丁冲突时失败，并写出冲突的补丁文件名。
- **升级演练闸门**：分支保护要求 `upgrade-drill` 这个 job 通过。它在签名之后运行，用的是正式签名的产物和正式的信任锚：

```
build.yml   host-toolchain -> firmware (ci) -> system-test (emulation, ephemeral keys)
            -> sign (release-signing, approval; bump PRs and main only)
            -> upgrade-drill -> publish (PR: prerelease, main: release)

upgrade-drill (emulation):
  base      = factory image of the latest stable release (or of this build if none exists yet)
  isp/inet  = datapath topology + fake GitHub Releases API serving this signed candidate
  steps     = push test config -> wrt-sync --candidate -> wrt-update -> reboot
              -> health check confirms the new slot -> config still present
  pass      = new slot confirmed; fail = rollback observed, job fails, nothing is published
```

- **为什么不再需要真机验证**：真机验证原本要确认三件事：新镜像能被旧系统接受并写入、新系统能启动并通过健康检查、配置能迁移过去。演练在同一个出货镜像、同一套信任锚上完成了这三件事。模拟器覆盖不了的只有硬件链路，而这部分已经由 A/B 回滚兜底。
- **备选方案**：
  - 维护者在设备上验证后写入状态（原方案）。否决，因为每周都要一次真机操作。
  - 让设备自动回报验证结果。否决，因为这需要设备持有能写 GitHub 状态的 token，增加攻击面。

### D6. 配置推送

- **私有仓库的结构**：

```
wrt-config (private repo)
  .sops.yaml                  age recipients (your workstation key)
  secrets/*.enc.yaml          pppoe, dae subscriptions, wg keys, tailscale authkey, smb users
  dae/*.dae(.enc)             user dae config (no lan_interface / wan_interface)
  pods/*.yaml                 pod specs
  uci/*.uci.tmpl              uci batch templates, filled from secrets at push time
```

- **命令**：`just config-init` 生成私有仓库的骨架；`just config-push <host>` 负责推送，私有仓库的位置由 `WRT_CONFIG_DIR` 指定。两者与脚本同名，符合 foundation 的“对象-动词”命名规则。推送依次执行：
  1. 用 sops 解密到临时目录，退出时清理；
  2. 渲染模板；
  3. 在本机校验：`uci` 的语法检查，以及在设备上用 `dae validate` 做一次预校验。预校验在设备的临时目录里进行，不改动任何现有配置；
  4. 计算每个服务的配置哈希，与设备上的记录比较，只推送并重载有变化的服务；
  5. 通过 `ssh -o PasswordAuthentication=no` 把文件传到设备并执行 `uci batch`；
  6. 如果某个服务重载失败，恢复它推送前的备份，再次重载，然后以非零状态退出。
- **跨升级保留**：推送写入的路径（`/etc/dae/user/`、`/etc/config/*` 中相关的项、Pod YAML 以外的本地文件）追加到镜像的 `/etc/sysupgrade.conf`，保证 A/B 升级后仍然保留。
- **为什么要加密**：私有仓库一旦泄露或误公开，明文密钥就全部暴露。sops 加 age 与 Nix 生态契合，解密只在工作站上进行。这一条是本设计补充的默认安全措施，探索阶段只确认过“密钥放在私有仓库”。

### D7. 验证方式

- **用例与规格一一对应**：
  - `tests/release/test_signing.py`：一部分在宿主上运行，静态审计工作流（只有 `sign` 引用 `release-signing`，签名 job 的步骤只有下载、`sign-tools` 和 `release-sign.sh`），并用临时密钥驱动 `release-sign.sh`；另一部分在模拟器里确认设备拒绝其他密钥签名的索引。
  - `tests/release/test_publishing.py`：宿主上驱动 `release-publish.sh`，覆盖附件、预发布与正式版的判断、运行标识不一致、说明文字。
  - `tests/release/test_device_sync.py`：模拟器用例，`inet` 里跑一个模拟的 GitHub Releases API（HTTPS，测试 CA 签发），同时阻断路由器 WAN 地址到它的直连。
  - `tests/release/test_upstream_bump.py`：宿主上用本地裸仓库充当三个上游，覆盖开 PR、不开 PR 和补丁冲突；升级演练的两个场景由 `upgrade-drill` 运行的用例标注。
  - `tests/ops/test_config_push.py`：用一次性的配置仓库和 age 测试密钥，对模拟器里的路由器执行 `just config-push`。
- **临时密钥夹具**：`wrt_tests/keys.py` 生成一次性的 apk EC 密钥和 usign 密钥，并提供两个夹具：
  - `signed_repo`：用 `release-sign.sh` 重新签名本次构建的产物；
  - `trust`：把对应的公钥写进路由器的测试 overlay，替换掉 `/etc/apk/keys` 里原有的公钥。
- **演练用例**：`upgrade-drill` job 运行的用例带有 `@target("emulation")`，并用 pytest 的 `-m drill` 单独选出。`system-test` 用临时密钥跑同一组用例，所以演练逻辑本身每次提交都被测到，签名之后只是换成正式密钥和正式信任锚再跑一遍。
- **GitHub 端的设置**：environment 的审批人和分支保护的必需检查项，属于 GitHub 仓库的设置，不在代码里。由 `scripts/github-audit.sh` 用 `gh api` 读取并核对，在 check 工作流里定期运行。
- **真机**：本 change 没有仅真机的场景。

## Risks / Trade-offs

- **[构建 job 被攻破时，当次产物可能已被篡改]** 这是签名隔离防不住的。→ 长期可以靠可复现构建和第三方重建比对来发现；短期由人工审批加上阅读 diff 把关。
- **[GitHub API 的速率限制或限流]** → 同步每天一次，并使用条件请求（ETag）。
- **[`apk adbsign` 的参数和行为]** → `release-sign.sh` 的最后一步用 `wrt-keyring` 里的公钥做一次校验，校验不通过就判为失败；`test_signing.py` 覆盖这条路径。
- **[演练用的上一个正式版本身有缺陷]** 例如旧版本的升级逻辑有 bug，演练就会一直失败。→ 这时由维护者判断，修复后发一个过渡版本；演练的基线始终是最新的正式版。
- **[模拟器覆盖不了硬件链路]** → 由 A/B 回滚兜底：真机升级后如果起不来，会自动回到上一个槽位。
- **[`BUILDBOT` 触发的工具链强制重建]** 只在工具链目录的 git 版本变化时发生，与缓存策略一致。
- **[手工推送配置时出错]** → 推送前校验、只重载有变化的服务、失败时回滚，三者结合。
- **[age 私钥丢失，密钥无法解密]** → 在工作站之外离线保存一份 age 密钥备份，写进 `docs/ops.md`。

## Migration Plan

1. 生成发布用的 apk EC 密钥对和 usign 密钥对。私钥存进 `release-signing` environment 的 secrets，公钥放进 `wrt-keyring`。
2. 建立私有配置仓库和 age 密钥，把现有配置迁移进去。
3. 第一次正式发布后刷写出厂镜像（其中已包含 `wrt-keyring`），然后运行一次 `just test-device`。之后的更新都走同步加 `wrt-update`。
4. 回退：`wrt-slot switch` 回到上一个槽位；本地仓库保留了最近 3 个版本，也可以指定用旧版本重新升级。

## Open Questions

- Release 的 tag 格式可以之后调整，不影响规格。
- 同步容器具体用哪个基础镜像，实施时选一个最小且维护良好的镜像，不影响规格。
