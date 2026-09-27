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
  - `r4s-ebpf-datapath` 让容器流量经过 dae。

## Goals / Non-Goals

**Goals:**
- 即使构建 job 被攻破，攻击者也拿不到能长期冒充发布者的密钥。
- 设备端的更新完全不依赖路由器本机直连 GitHub。
- 每周 bump 有一道人工把关的验证闸门，同时尽量减少手工操作。

**Non-Goals:**
- 在构建 job 被攻破的情况下，保证当次构建产物本身的完整性。这需要可复现构建加上第三方重建比对，不在本 change 范围内。
- 自建软件源服务器或 CDN。
- 多台设备的批量管理。

## Decisions

### D1. 两种构建形态和信任锚

- **正式版的 seed**：`config/release.seed` 在 ci profile 的基础上增加：

```
CONFIG_BUILDBOT=y
# CONFIG_PACKAGE_openwrt-keyring is not set
CONFIG_PACKAGE_wrt-keyring=y
# CONFIG_SIGN_FIRMWARE is not set
```

- **`wrt-keyring` 包**：放在自有 feed 里，安装 `/etc/apk/keys/wrt-release-<id>.pem`（apk 用的 EC 公钥）和 usign 公钥。支持同时放多把，用于轮换。
- **构建过程中的签名**：构建时仍然会生成一把一次性的 apk 私钥，给构建内部的安装和建索引用。因为打开了 `BUILDBOT`，这把钥匙的公钥不会进镜像。构建时也不给固件签名。
- **开发版**：dev profile 不开 `BUILDBOT`，沿用上游行为，镜像信任本地构建的密钥。这类镜像只用于调试，不会发布。
- **备选方案**：给 base-files 打补丁，跳过安装构建公钥。否决，因为上游已经有 `BUILDBOT` 这条现成的路径。

### D2. 签名 job

```
job sign  (needs: firmware; environment: release-signing -> required reviewer)
  1. download unsigned artifacts + manifest.json from the firmware job
  2. verify every artifact's sha256 against manifest.json  (mismatch -> abort)
  3. nix run .#sign-tools   (apk-tools v3, usign, ucert, fwtool built by Nix from
                             pinned first-party sources; no package build, no feeds)
  4. apk adbsign --sign-key $APK_KEY  every packages.adb
  5. usign -S + ucert + fwtool -S  on factory image and upgrade tar
  6. write SHA256SUMS, upload signed set for the publish job
```

- **签名工具的来源**：签名工具由 flake 用固定版本的源码自行构建，不使用构建 job 产出的宿主工具。那些工具出自可能被攻破的 job，拿来签名就等于绕开了隔离。
- **密钥存放**：两把私钥存为 `release-signing` 这个 environment 的 secrets，只有这个 environment 能读到。这个 environment 设置了必需的审批人，满足“每次签名都需要人工审批”。
- **备选方案**：
  - 在本机签名。探索阶段已经决定不用。
  - 在构建 job 里签名。否决，理由见 proposal。

### D3. 发布

`publish` job 在 `sign` 之后执行：

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

- **容器不需要被信任**：完整性由宿主这边用镜像里的发布公钥校验。所以同步容器可以用第三方的最小镜像，它只负责下载。
- **原子切换**：新版本先下载到 `.incoming`，全部校验通过后才改 `current` 这个符号链接。
- **apk 源列表**：`/etc/apk/repositories.d/distfeeds.list` 被覆盖，改为指向 `current` 下的本地仓库，路径是 `file` 形式的 `packages.adb`。
- **本地升级**：`wrt-update` 调用 sysupgrade 升级到 `current` 里的升级 tar。
- **签名强制检查**：`platform_check_image`（来自 A/B 那个 change）额外要求镜像必须带有效签名。在 `REQUIRE_IMAGE_METADATA` 的基础上，用 ucert 对照镜像里的公钥校验。

### D5. 每周 bump

- **定时工作流**：每周一执行，读取三个上游仓库 main 的 HEAD。有变化就更新 `upstream.lock`，用 GitHub App 或默认的 token 开 PR。PR 描述里写入新旧 SHA，以及 `git log --oneline` 的摘要，最多 50 行。
- **PR 的检查**：foundation 的 CI 会在补丁冲突时失败，并写出冲突的补丁文件名。
- **设备验证闸门**：分支保护要求一个名为 `device-verified` 的状态检查。它由维护者在设备上验证通过后执行 `just verify-pr <n>` 写入，底层通过 `gh api` 设置 commit status。
- **备选方案**：让设备自动回报验证结果。否决，因为这需要设备持有能写 GitHub 状态的 token，增加攻击面。

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

- **推送命令**：本仓库的 `just push <host>` 依次执行：
  1. 用 sops 解密到临时目录，退出时清理；
  2. 渲染模板；
  3. 在本机校验：`uci` 的语法检查，以及在设备上用 `dae validate` 做一次预校验。预校验在设备的临时目录里进行，不改动任何现有配置；
  4. 计算每个服务的配置哈希，与设备上的记录比较，只推送并重载有变化的服务；
  5. 通过 `ssh -o PasswordAuthentication=no` 把文件传到设备并执行 `uci batch`；
  6. 如果某个服务重载失败，恢复它推送前的备份，再次重载，然后以非零状态退出。
- **跨升级保留**：推送写入的路径（`/etc/dae/user/`、`/etc/config/*` 中相关的项、Pod YAML 以外的本地文件）追加到镜像的 `/etc/sysupgrade.conf`，保证 A/B 升级后仍然保留。
- **为什么要加密**：私有仓库一旦泄露或误公开，明文密钥就全部暴露。sops 加 age 与 Nix 生态契合，解密只在工作站上进行。这一条是本设计补充的默认安全措施，探索阶段只确认过“密钥放在私有仓库”。

## Risks / Trade-offs

- **[构建 job 被攻破时，当次产物可能已被篡改]** 这是签名隔离防不住的。→ 长期可以靠可复现构建和第三方重建比对来发现；短期由人工审批加上阅读 diff 把关。
- **[GitHub API 的速率限制或限流]** → 同步每天一次，并使用条件请求（ETag）。
- **[`apk adbsign` 的参数和行为]** → 实施时在签名 job 里加一步，用镜像里的发布公钥做一次校验，校验不通过就判为失败。
- **[`BUILDBOT` 触发的工具链强制重建]** 只在工具链目录的 git 版本变化时发生，与缓存策略一致。
- **[手工推送配置时出错]** → 推送前校验、只重载有变化的服务、失败时回滚，三者结合。
- **[age 私钥丢失，密钥无法解密]** → 在工作站之外离线保存一份 age 密钥备份，写进 `docs/ops.md`。

## Migration Plan

1. 生成发布用的 apk EC 密钥对和 usign 密钥对。私钥存进 `release-signing` environment 的 secrets，公钥放进 `wrt-keyring`。
2. 建立私有配置仓库和 age 密钥，把现有配置迁移进去。
3. 第一次正式发布后刷写出厂镜像（其中已包含 `wrt-keyring`），之后的更新都走同步加 `wrt-update`。
4. 回退：`wrt-slot switch` 回到上一个槽位；本地仓库保留了最近 3 个版本，也可以指定用旧版本重新升级。

## Open Questions

- Release 的 tag 格式可以之后调整，不影响规格。
- 同步容器具体用哪个基础镜像，实施时选一个最小且维护良好的镜像，不影响规格。
