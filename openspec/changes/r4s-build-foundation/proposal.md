# Proposal

## Why

要为 NanoPi R4S（4GB LPDDR4）做一套自有的 OpenWrt 固件。参考对象 sbwml/r4s_build_script 以官方 v25.12.5 为骨架，但做法既无法复现，也无法审计：

- rockchip 和 generic 两个 target 被替换成需要授权才能访问的私有仓库；
- 84 次 `git clone` 都拉分支 HEAD，没有一次固定到提交；
- 构建时有 229 次 `curl` 远程拉取脚本和补丁，另有 118 处 `sed -i` 修改上游文本；
- 子脚本以 `bash xxx.sh` 的方式调用，shebang 里的 `-e` 不生效，失败会被静默吞掉。

另一方面，上游 main（2026-09-27，`1019293`）已经原生提供 rockchip 6.18.52 内核、U-Boot 2026.07、TF-A 2.15、EROFS 根文件系统（fstools 已支持在块设备上把 overlay 接在 EROFS 之后），以及 apk 3.0.5。所以自建基础只需要一层很薄的补丁。

固件每周都要跟进上游，靠人工上机验证既慢又不可重复。验证必须尽量自动化，而且要在模拟器里运行**真正出货的镜像**，真机只做模拟器无法覆盖的少量硬件检查。

## What Changes

- **基线与固定版本**
  - 以 `openwrt/openwrt` main 为基线。
  - `upstream.lock` 把 openwrt、packages、luci 三个仓库固定到提交 SHA，初始为 `1019293`。
- **补丁与配置**
  - 补丁放在 `patches/<repo>/*.patch`，用 `git am` 应用，任一失败即中止。
  - 构建过程中不联网拉取脚本或补丁，也不用 `sed` 改上游文本。
  - 软件包配置由 `config/*.seed` 这些 diffconfig 片段组合而成，执行 `make defconfig` 后逐行校验。
  - 上游没有开放成 `CONFIG_KERNEL_*` 的内核选项，统一写进内核配置叠加文件 `config/kernel.config`。这个文件链接到上游原生支持的 `env/kernel-config`，构建完成后逐行校验。
- **构建环境与编排**
  - Nix flake（`buildFHSEnv`）定义宿主机工具，本机和 CI 共用同一份。本机用 OrbStack 的 NixOS 虚拟机，构建目录放在外接 SSD 上。
  - 构建只能在 Linux 宿主机上进行：`KERNEL_DEBUG_INFO_BTF` 和 `tools/dwarves` 在 macOS 上不可用。
  - 编排入口统一用 `just` + POSIX sh。命令和脚本按动词对称命名，例如 fetch/patch/config/build/test、mount/unmount、pack/unpack。
- **工具链**
  - GCC 15 + LTO + mold + gc-sections。
  - `-O2 -mcpu=cortex-a72.cortex-a53+crypto` 通过 `CONFIG_EXTRA_OPTIMIZATION` 注入，不修改 `include/target.mk`。
- **内核**
  - 使用上游默认的 6.18。
  - 打开 BTF、`BPF_EVENTS`、`CGROUPS`/`CGROUP_BPF`；只用 cgroup v2。
  - EROFS 编进内核；打开 F2FS 压缩，其中 zstd 和 lz4 启用。
  - 默认拥塞控制用 BBRv3 + fq，采用 sbwml 的 6.18 移植，20 个补丁全部保留。
  - 出货内核内置 QEMU `virt` 平台需要的少量驱动（PL011 串口、通用 PCIe 主机控制器、virtio 磁盘和网卡、i6300esb 看门狗），使同一个内核可以在模拟器里启动。
- **根文件系统**
  - EROFS（`lz4hc,12`），不再生成 squashfs。
  - overlay 用 f2fs，启动参数里加上 `fstools_overlay_compression_type=zstd` 开启压缩。
  - 本 change 产出单槽镜像，沿用上游分区布局；A/B 由 `r4s-ab-rollback` 负责。
- **基础系统**
  - LAN 地址 10.0.0.1；LuCI 用 uhttpd + ucode，带简体中文语言包，界面语言跟随浏览器。
  - 登录 shell 保持 ash，交互式会话自动进入 zsh（预装 autosuggestions 和 syntax-highlighting 两个插件）；镜像同时提供 bash。
  - zram-swap 1 GiB，zstd 压缩；镜像里不预置 root 密码。
- **不采用**：UPX、LRNG、urngd、shortcut-fe、natflow、PCRE1、zh-cn 翻译转换脚本、opkg 补丁、i915 实时内核补丁、用 nginx/uwsgi 跑 LuCI，以及伪造 vermagic。
- **自动化系统测试**
  - 测试套件基于 pytest + labgrid，Python 环境由 uv 管理并锁定，格式化用 ruff，类型检查用 ty。
  - 同一份用例既能在模拟器里运行，也能在真机上运行；每条可测试的规格场景都对应一个测试。
  - 模拟器里运行的是出货镜像本身：内核从镜像的 FIT 中提取，启动参数取自镜像里的 `boot.scr`，机器以 R4S 的板型身份（`friendlyarm,nanopi-r4s`）启动，网络在无 root 权限的用户命名空间里搭建。
  - 真机验证压缩为：刷机之后运行 `just test-device <host>`，再加少数几项硬件专属检查。
- **代码规范**
  - 以下检查全部强制执行，CI 不通过就算失败：shfmt、shellcheck、nixfmt、ruff format/check、ty、actionlint、editorconfig，以及禁止模式检查。
  - 所有脚本使用统一骨架；`just check` 做全量检查，`just fmt` 统一格式化。
- **CI**
  - 公开 GitHub 仓库 + GitHub 托管 runner。
  - 包含四个 job：`check`（规范检查）、`host-toolchain`（按输入哈希缓存）、`firmware`（`ALL_KMODS`）、`system-test`（模拟器）。每个 job 都控制在 6 小时以内。
  - 正式镜像和 kmod 仓库必须出自同一次构建。
  - 签名和发布由 `r4s-release-pipeline` 负责。
- **上游贡献**（只在本地准备好，提交前需要维护者明确同意）：
  - `include/image.mk:110` 判断的配置项名写错了，导致 EROFS 的 LZMA 分支永远走不到。修正方式是新增一个默认 lz4hc 的压缩算法选择项。
  - 为 F2FS 压缩的各个选项增加对应的 `KERNEL_*` 开关。

## Capabilities

### New Capabilities

- `build/environment`：可复现的 Linux 构建环境。Nix flake 保证本机虚拟机和 CI 一致，统一用 just 作为入口。
- `build/upstream-pinning`：上游源码和 feeds 固定到 SHA，以及补丁队列的应用方式和失败处理。
- `build/ci`：分阶段 CI、缓存、全量 kmod 的产出，以及“镜像与 kmod 出自同一次构建”的约束。
- `firmware/toolchain`：目标工具链的版本和编译优化选项。
- `firmware/kernel`：内核版本、必需的内核特性（BTF、cgroup v2、EROFS、F2FS 压缩、模拟平台驱动），以及 BBRv3。
- `firmware/rootfs`：EROFS 根文件系统和 f2fs zstd overlay 的布局与行为。
- `firmware/base-system`：出厂默认值（LAN 地址、Web 界面、语言、shell、zram、密码策略）和不采用的组件清单。
- `testing/harness`：测试套件、规格场景与测试的对应关系、模拟器和真机两种目标，以及 Python 工具链。
- `testing/emulation`：在 QEMU 中以 R4S 身份启动出货镜像，并提供网络拓扑和故障注入。
- `quality/code-standards`：格式化、静态检查、统一的脚本骨架与对称命名，以及在 CI 中强制执行。

### Modified Capabilities

（无。项目目前还没有已有规格。）

## Impact

- **新增目录和文件**：`flake.nix`、`justfile`、`upstream.lock`、`patches/`、`config/`（包括 `kernel.config`）、`files/`、`feed/`、`tests/`（pyproject、uv.lock、labgrid 目标、用例）、`.editorconfig`、`.shellcheckrc`、`.github/workflows/`。
- **外部依赖**：
  - OrbStack 的 NixOS 虚拟机和外接 SSD。虚拟机里没有 KVM，本机的 QEMU 走 TCG 纯软件模拟。
  - GitHub Actions 托管 runner。
  - PyPI（通过 uv.lock 固定版本并校验哈希）。
- **kmod 来源**：内核是自己编的，官方源的 kmod 装不上，所有 kmod 都来自本项目的仓库。
- **需要长期维护的内核源码补丁**：BBRv3 改动的是 TCP 核心，每次 6.18.y 升级都可能要重整。
- **出货内核变化**：多了几个 virt 平台驱动，体积约增加 100～300 KB；在 R4S 上这些驱动不会被加载。
- **补丁层变化**：删除原先给 `Config-kernel.in` 加 F2FS 选项的补丁 0001，改用内核配置叠加文件。补丁只剩 BBRv3 和启动脚本两个。
- **依赖本 change 的后续 change**：`r4s-ab-rollback`、`r4s-ebpf-datapath`、`r4s-services`、`r4s-release-pipeline`。它们的验证都建立在这里的测试框架和模拟环境之上。
