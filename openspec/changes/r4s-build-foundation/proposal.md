# Proposal

## Why

要为 NanoPi R4S（4GB LPDDR4）做一套自有的 OpenWrt 固件。参考对象 sbwml/r4s_build_script 以官方 v25.12.5 为骨架，但做法无法复现，也无法审计：
- rockchip 和 generic 两个 target 被替换成需要授权才能访问的私有仓库；
- 84 次 `git clone` 都拉分支 HEAD，没有一次固定到提交；
- 构建时 229 次 `curl` 远程拉取脚本和补丁，另有 118 处 `sed -i` 修改上游文本；
- 子脚本以 `bash xxx.sh` 方式调用，shebang 里的 `-e` 不生效，失败会被静默吞掉。

另一方面，上游 main（2026-09-27，`1019293`）已经原生提供 rockchip 6.18.52 内核、U-Boot 2026.07、TF-A 2.15、EROFS 根文件系统（fstools 已支持在块设备上把 overlay 接在 EROFS 之后），以及 apk 3.0.5。所以自建基础只需要一层很薄的补丁。

## What Changes

- **基线与固定版本**
  - 以 `openwrt/openwrt` main 为基线。`upstream.lock` 固定 openwrt、packages、luci 三个仓库的提交 SHA，初始候选为 `1019293`。
- **补丁与配置**
  - 补丁放在 `patches/<repo>/*.patch`，用 `git am` 应用，任一失败即中止。
  - 构建过程中不得联网拉取脚本或补丁，也不得用 `sed` 改上游文本。
  - 配置由 `config/*.seed` diffconfig 片段组合而成，执行 `make defconfig` 后校验结果与 seed 一致。
- **构建环境与编排**
  - 用 Nix flake（`buildFHSEnv`）定义宿主机工具，本机和 CI 共用同一份。本机用 OrbStack 的 NixOS 虚拟机，构建目录放在外接 SSD 上。
  - 构建必须在 Linux 宿主机上进行：`KERNEL_DEBUG_INFO_BTF` 和 `tools/dwarves` 在 macOS 上不可用。
  - 编排入口用 `just` + POSIX sh（fetch / patch / config / build）。
- **工具链**
  - GCC 15 + LTO + mold + gc-sections。
  - `-O2 -mcpu=cortex-a72.cortex-a53+crypto` 通过 `CONFIG_EXTRA_OPTIMIZATION` 注入，不修改 `include/target.mk`。
- **内核**
  - 使用上游默认的 6.18。
  - 打开 BTF（同时关闭 `DEBUG_INFO_REDUCED`）、`BPF_EVENTS`、`CGROUPS`/`CGROUP_BPF`；只用 cgroup v2，不开 `MEMCG_V1`。
  - EROFS 编进内核；打开 `F2FS_FS_COMPRESSION`，支持 zstd。
  - 默认拥塞控制用 BBRv3 + fq。BBRv3 补丁采用 sbwml 的 6.18 移植，去掉 x86 专用的那个，共 19 个。
- **根文件系统**
  - 根文件系统用 EROFS（`lz4hc,12`），不再生成 squashfs。
  - overlay 用 f2fs，在启动参数里加 `fstools_overlay_compression_type=zstd` 开启压缩。
  - 本 change 产出的是单槽镜像，沿用上游分区布局；A/B 由 `r4s-ab-rollback` 负责。
- **基础系统**
  - LAN 地址 10.0.0.1。
  - LuCI 用 uhttpd + ucode，界面为简体中文。
  - root 的登录 shell 保持 ash；交互式会话自动 `exec zsh`，并预装 autosuggestions 和 syntax-highlighting 两个插件。
  - zram-swap 1 GiB，zstd 压缩。
  - 镜像里不预置 root 密码。
- **不采用**：UPX、LRNG、urngd、shortcut-fe、natflow、PCRE1、zh-cn 翻译转换脚本、opkg 补丁、i915 实时内核补丁、用 nginx/uwsgi 跑 LuCI，以及伪造 vermagic。
- **CI**
  - 公开 GitHub 仓库 + GitHub 托管 runner。
  - 构建按 toolchain → packages（`ALL_KMODS`）→ images 三个阶段拆开，每个阶段控制在 6 小时以内。工具链和 ccache 以 lock 文件的哈希作为缓存键。
  - 正式镜像和 kmod 仓库必须出自同一次构建，保证 vermagic 一致。
  - 签名和发布由 `r4s-release-pipeline` 负责。
- **上游贡献**：向上游提交 `include/image.mk:110` 的修正。那里判断的是 `CONFIG_EROFS_FS_ZIP_LZMA`，但实际的配置项名是 `KERNEL_EROFS_FS_ZIP_LZMA`，导致 LZMA 分支永远不会被用到。

## Capabilities

### New Capabilities

- `build/environment`：可复现的 Linux 构建环境。Nix flake 保证本机虚拟机和 CI 一致，统一用 just 作为入口。
- `build/upstream-pinning`：上游源码和 feeds 固定到 SHA，补丁队列的应用方式和失败处理。
- `build/ci`：分阶段 CI、缓存、全量 kmod 的产出，以及“镜像与 kmod 出自同一次构建”的约束。
- `firmware/toolchain`：目标工具链的版本和编译优化选项。
- `firmware/kernel`：内核版本、必需的内核特性（BTF、cgroup v2、EROFS、F2FS 压缩），以及 BBRv3。
- `firmware/rootfs`：EROFS 根文件系统和 f2fs zstd overlay 的布局与行为。
- `firmware/base-system`：出厂默认值（LAN 地址、Web 界面、语言、shell、zram、密码策略）和不采用的组件清单。

### Modified Capabilities

（无。项目目前还没有已有规格。）

## Impact

- **新增目录和文件**：`flake.nix`、`justfile`、`upstream.lock`、`patches/`、`config/`、`files/`、`feed/`、`.github/workflows/`。
- **外部依赖**：OrbStack 的 NixOS 虚拟机加外接 SSD；GitHub Actions 托管 runner（公开仓库）。
- **kmod 来源**：内核是自己编的，官方源的 kmod 装不上，所有 kmod 都来自本项目的仓库。
- **需要长期维护的内核源码补丁**：BBRv3 改动 TCP 核心（`include/net/tcp.h`、`tcp_input.c`、`tcp_output.c`、`tcp_rate.c`、`tcp_bbr.c`），每次 6.18.y 升级都可能需要重整。
- **依赖本 change 的后续 change**：`r4s-ab-rollback`、`r4s-ebpf-datapath`、`r4s-services`、`r4s-release-pipeline`。
