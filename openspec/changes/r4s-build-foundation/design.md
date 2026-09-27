# Design

## Context

动机见 proposal.md 的 Why 一节。本设计依赖以下现状和约束：

- **仓库现状**：仓库里目前只有 `openspec/`，没有任何构建代码。
- **上游 main（`1019293`，2026-09-27）**，下面的事实都在上游源码里核对过：
  - rockchip 默认内核是 6.18.52（`target/linux/rockchip/Makefile`）。
  - U-Boot 2026.07、TF-A 2.15.0、erofs-utils 1.9.4、apk 3.0.5、musl 1.2.6。
  - GCC 默认 14，15 可选（`toolchain/gcc/Config.version`）。
  - llvm-bpf 22.1.3，dwarves（pahole）1.31。
- **R4S 设备定义**：上游的 `friendlyarm_nanopi-r4s` 本身就是 “4GB LPDDR4” 这个型号（`target/linux/rockchip/image/armv8.mk:139-145`）。
- **宿主机**：M1 Max、32 GB 内存，macOS 上装了 OrbStack，系统盘只剩约 109 GiB。
  - `KERNEL_DEBUG_INFO_BTF` 写明了 `depends on !HOST_OS_MACOS`（`config/Config-kernel.in:566`）。
  - dwarves 在 Darwin 上会被跳过（`tools/Makefile:151-156`）。
  - mold 同样依赖 `!HOST_OS_MACOS`（`config/Config-build.in`）。
  - 所以构建只能在 Linux 上进行。
- **GitHub 托管 runner 的限制**：每个 job 最长 6 小时；标准 Linux runner 是 4 核、16 GB；缓存总量上限 10 GB。

## Goals / Non-Goals

**Goals:**
- 在 lock 相同的前提下，本机和 CI 产出的源码树和配置完全一致，构建时间戳也一致。
- 产出一个能在 R4S 上启动的单槽 SD 镜像，以及同一次构建产出的全量 kmod 仓库。
- 补丁层保持在少数几个文件，其中大部分可以提交给上游。

**Non-Goals:**
- A/B 分区和回滚，由 `r4s-ab-rollback` 负责。
- dae、einat、qosify 等数据面组件，由 `r4s-ebpf-datapath` 负责。
- 数据盘和各类服务，由 `r4s-services` 负责。
- 签名、发布和设备端同步，由 `r4s-release-pipeline` 负责。本 change 的 CI 只产出未签名的产物。
- 用 `-mcpu` 调优内核本身，内核保持上游默认的编译参数。
- 硬件卸载。R4S 没有这类硬件。

## Decisions

### D1. 仓库布局：构建目录放在仓库外

```
wrt-build/                      (this repo)
  flake.nix  flake.lock         host environment
  justfile                      entry points
  upstream.lock                 openwrt / packages / luci: url, sha, commit epoch
  patches/openwrt/*.patch       git format-patch series, applied with git am
  patches/packages/*.patch
  patches/luci/*.patch
  feed/                         own packages (added as src-link)
  config/*.seed                 diffconfig fragments
  files/                        rootfs overlay (profile.d, sysctl.d, uci-defaults)
  scripts/*.sh                  POSIX sh helpers called by just
  .github/workflows/
  docs/

$WRT_WORKDIR/                   (outside repo; external SSD locally, /builder on CI)
  openwrt/  dl/  ccache/  out/
```

- **做法**：构建目录由 `WRT_WORKDIR` 指定。
- **理由**：OpenWrt 的源码树加上构建产物有几十到上百 GB，而且要求文件系统区分大小写。放在仓库外面，仓库本身就保持干净。
- **备选方案**：把 openwrt 作为 git submodule 放进仓库。否决，因为补丁会把 submodule 弄脏，而且 submodule 放不到外接盘上。

### D2. 按 SHA 获取上游，feeds 也固定到提交

- **openwrt**：用 `git init` 加 `git fetch --depth 1 origin <sha>` 取到指定提交。GitHub 支持按 SHA 获取。
- **feeds**：生成 `feeds.conf`，格式是 `src-git packages <url>^<sha>`。`scripts/feeds:228` 会按 `^` 拆出提交，所以原生就支持。自有 feed 用 `src-link wrtbuild <repo>/feed` 加入。
- **备选方案**：沿用 `feeds.conf.default` 里的分支名。否决，因为那样无法复现。

### D3. 补丁用 git am 应用，并固定身份和时间

- **做法**：
  - `scripts/patch.sh` 对每个仓库按文件名顺序执行 `git am`。
  - 执行前固定 `GIT_COMMITTER_NAME`、`GIT_COMMITTER_EMAIL`，并用 `GIT_COMMITTER_DATE` 取补丁里的作者时间。这样源码树的提交 SHA 在任何时候应用都一样。
  - 任何一个补丁失败，就先 `git am --abort` 再退出，并报出补丁文件名。
  - feeds 的补丁在 `./scripts/feeds update -a` 之后，应用到 `feeds/<name>` 这些 git 检出目录上。
- **备选方案**：quilt，或者 `patch -p1`。否决。quilt 多一层工具。`patch -p1` 做不到“要么全部应用、要么全部不应用”。sbwml 用的 `curl | patch` 失败时也不会中止。

### D4. SOURCE_DATE_EPOCH 从 lock 文件取

- **做法**：`upstream.lock` 里记录 openwrt 那个提交的时间戳。`fetch.sh` 把它写进源码树根目录的 `version.date`。
- **理由**：`scripts/get_source_date_epoch.sh` 会先找 `version.date`（`try_version`），找不到才去读 git 日志。如果不这么做，`git am` 生成的提交时间就会成为构建时间戳，每次都不一样。

### D5. seed 配置片段 + defconfig + 校验

`config/` 下的片段：

- `target.seed`：rockchip/armv8 和 nanopi-r4s。
- `toolchain.seed`、`kernel.seed`、`rootfs.seed`、`system.seed`。
- `ci.seed`：打开 `ALL_KMODS` 和 ccache。
- `dev.seed`：本机精简构建用。

做法是按 profile 把这些片段拼起来，执行 `make defconfig`，然后逐行检查 seed 里的每一行（包括 `# ... is not set`）在最终的 `.config` 里是否原样存在。有任何一行被丢掉就失败，这样上游改名或删掉某个选项时，能第一时间发现。最后用 `scripts/diffconfig.sh` 的输出作为产物，方便审阅。

### D5 附：seed 里各项选项的来源

**toolchain.seed**（依据：`rules.mk:256` 中 `TARGET_CFLAGS = TARGET_OPTIMIZATION + EXTRA_OPTIMIZATION`，后面的 `-O`/`-mcpu` 会覆盖前面的）

```
CONFIG_DEVEL=y
CONFIG_TOOLCHAINOPTS=y
CONFIG_GCC_USE_VERSION_15=y
CONFIG_USE_LTO=y
CONFIG_USE_GC_SECTIONS=y
CONFIG_USE_MOLD=y
CONFIG_EXTRA_OPTIMIZATION="-fno-caller-saves -fno-plt -O2 -mcpu=cortex-a72.cortex-a53+crypto"
CONFIG_BPF_TOOLCHAIN_HOST=y
```

`BPF_TOOLCHAIN_HOST` 用 flake 固定的宿主 clang 编译 BPF 对象，省掉从源码编 llvm-bpf 的大约 1 小时（`toolchain/Config.in:41-72`）。

**kernel.seed**（依据：`include/kernel-defaults.mk:118-119` 会把 `.config` 里的 `CONFIG_KERNEL_*` 原样改名写进内核配置，但前提是这个选项在 Kconfig 里已经定义）

```
CONFIG_KERNEL_DEBUG_INFO=y
# CONFIG_KERNEL_DEBUG_INFO_REDUCED is not set
CONFIG_KERNEL_DEBUG_INFO_BTF=y
CONFIG_KERNEL_BPF_EVENTS=y
CONFIG_KERNEL_CGROUPS=y
CONFIG_KERNEL_CGROUP_BPF=y
# CONFIG_KERNEL_MEMCG_V1 is not set
CONFIG_KERNEL_F2FS_FS_COMPRESSION=y
CONFIG_PACKAGE_kmod-tcp-bbr=y
CONFIG_PACKAGE_kmod-sched=y
```

- `KERNEL_F2FS_FS_COMPRESSION` 目前上游没有，要由 D7 的补丁加进来，其中带 zstd。
- tcx 不用另外开：`NET_XGRESS` 已经内置在 rockchip 的配置里（`armv8/config-6.18:442-447`）。
- `MODULE_ALLOW_BTF_MISMATCH` 保持关闭，因为所有 kmod 都出自同一次构建。

**rootfs.seed**

```
CONFIG_TARGET_ROOTFS_EROFS=y
# CONFIG_TARGET_ROOTFS_SQUASHFS is not set
# CONFIG_TARGET_ROOTFS_EXT4FS is not set
CONFIG_TARGET_ROOTFS_PARTSIZE=1024
```

- `TARGET_ROOTFS_EROFS` 会自动选中 `KERNEL_EROFS_FS`。
- 压缩方式保持 `image.mk:109` 的 `lz4hc,12`。

**system.seed**（依据：`package/base-files/Makefile:96-103`）

```
CONFIG_TARGET_PREINIT_IP="10.0.0.1"
CONFIG_TARGET_PREINIT_BROADCAST="10.0.0.255"
CONFIG_TARGET_DEFAULT_LAN_IP_FROM_PREINIT=y
CONFIG_PACKAGE_luci=y
CONFIG_LUCI_LANG_zh_Hans=y
# CONFIG_PACKAGE_urngd is not set
CONFIG_PACKAGE_zram-swap=y
CONFIG_PACKAGE_zsh=y
CONFIG_PACKAGE_zsh-plugins=y
```

`DEFAULT_LAN_IP_FROM_PREINIT` 会生成 `board.d/99-lan-ip`。这个文件只在生成默认配置时起作用，所以保留配置升级时不会覆盖用户设置的地址，满足 base-system 规格；同时故障安全模式的地址也会变成 10.0.0.1。

### D6. 工具链只靠配置，不改 include/target.mk

- **做法**：见上面的 toolchain.seed。
- **备选方案**：像 sbwml 那样给 `include/target.mk` 打补丁把 `-Os` 改成 `-O2`。否决，因为靠配置就能达到同样效果。
- **LTO 失败怎么处理**：某个包开 LTO 编不过时，在它自己的 Makefile 里加 `PKG_BUILD_FLAGS:=no-lto`。这个修改以补丁的形式放进 `patches/packages`，并记到 `docs/lto-optouts.md` 里。

### D7. 内核：只打两类补丁

1. **`patches/openwrt/0001-config-kernel-add-F2FS-compression-options.patch`**
   - 在 `config/Config-kernel.in` 里加入 `KERNEL_F2FS_FS_COMPRESSION`，以及 `KERNEL_F2FS_FS_ZSTD`、`KERNEL_F2FS_FS_LZ4`。
   - 这是新增配置选项，不改内核源码，可以提交给上游。
   - **备选方案**：直接修改 `target/linux/rockchip/armv8/config-6.18`。否决，因为这个文件跟着上游经常变动，补丁很容易打不上。
2. **`patches/openwrt/0002-generic-add-BBRv3-for-6.18.patch`**
   - 把 sbwml 的 20 个 `010-bbr3-*.patch` 原样加到 `target/linux/generic/hack-6.18/`。
   - 第 0019 个必须保留：它修改的是通用的 `net/ipv4/bpf_tcp_ca.c`，BBRv3 把 `min_tso_segs` 改成了 `tso_segs` 并新增了 `skb_marked_lost`，缺了它 BPF struct_ops 就编译不过。
   - 继续用上游的 `kmod-tcp-bbr` 打包，模块文件仍然是 `tcp_bbr.ko`。第 0016 个补丁定义了 `BBR_VERSION 3` 和 `MODULE_VERSION`，所以可以在设备上核对版本号。
   - `kmod-tcp-bbr` 自带的 sysctl 已经会设置 `tcp_congestion_control=bbr`。另外在 `files/etc/sysctl.d/13-default-qdisc.conf` 里写上 `net.core.default_qdisc=fq`。`sch_fq` 由 `kmod-sched` 提供（`netsupport.mk:1010`）。

### D8. overlay 压缩通过启动参数打开

- **做法**：补丁 `0003-rockchip-bootscript-enable-f2fs-zstd-overlay.patch` 在 `target/linux/rockchip/image/default.bootscript` 的 bootargs 里加上 `fstools_overlay_compression_type=zstd`。
- **依据**：fstools 的 `libfstools/common.c:157-165` 和 `overlay.c:292-297` 会读这个参数，据此用 `-O extra_attr,compression` 格式化，并以 `compress_algorithm=zstd:3` 挂载。
- **影响范围**：这个修改会影响所有 rockchip 设备，但本项目只构建 R4S，可以接受。等 A/B 那个 change 落地后，启动脚本还会再改一次。

### D9. 交互 shell 与 zram

- **zsh 的切换方式**：
  - `files/etc/profile.d/99-zsh.sh` 只在交互式登录 shell 里生效：`$-` 含 `i`、标准输入是终端、zsh 可执行时，才执行 `exec /usr/bin/zsh -l`。
  - 非交互式的 SSH 命令不会读 `/etc/profile`，所以不会进 zsh。
  - 登录 shell 保持 ash。
- **zsh 插件**：自有 feed 里的 `zsh-plugins` 包把 zsh-autosuggestions 和 zsh-syntax-highlighting 固定到指定标签并校验哈希，由全局 zshrc 加载。
- **zram**：用一个 uci-defaults 脚本设置 `system.@system[0].zram_size_mb=1024` 和 `zram_comp_algo=zstd`，只在这两项尚未设置时才写入，这样保留配置升级时不会覆盖用户的设置。依据：`zram.init:17-69` 就是读这两个选项。

### D10. 本机构建目录：外接 SSD 上的 ext4 镜像文件

- **做法**：
  - 在外接 SSD 上建一个 ext4 镜像文件，由 OrbStack 的 NixOS 虚拟机通过 virtiofs 看到它，再 loop 挂载成 `WRT_WORKDIR`。
  - 这样 OpenWrt 构建里大量小文件的读写都落在 Linux 原生的 ext4 上，virtiofs 只承担大块读写，同时也自然满足了区分大小写的要求。
- **备选方案**：
  - 直接在 virtiofs 挂载的 APFS 区分大小写卷上构建。作为退路保留，但预期小文件性能差很多。
  - 放在虚拟机自己的磁盘里。否决，因为那样占用的是 macOS 系统盘的空间。

### D11. CI：宿主工具与工具链一个阶段，固件一个阶段

```
job host-toolchain (timeout 330m)
  key = hash(git rev-parse <owrt>:tools, <owrt>:toolchain,
             <pkgs>:lang/golang, <pkgs>:lang/rust,
             config/toolchain.seed, flake.lock)
  hit  -> done
  miss -> fetch, patch, config
          -> make tools/install toolchain/install + host packages (golang, rust)
          -> save staging_dir/{host,hostpkg,toolchain-*} as zstd tarball

job firmware (needs host-toolchain, timeout 330m)
  restore toolchain tarball (touch restored files so make does not rebuild them)
  restore ccache, dl/ caches
  fetch, patch, config (ci profile: ALL_KMODS)
  make world -> images + packages repo
  write manifest.json: run id, lock hash, kernel vermagic, image and index sha256
  upload unsigned artifacts
```

- **环境**：Nix 用 DeterminateSystems 的 installer 安装，flake 的闭包用缓存加速。开始前先清理 runner 的磁盘，腾出大约 70 GB 以上的空间。
- **缓存放不下怎么办**：如果工具链缓存和 ccache 加起来超过 10 GB 的缓存上限，就把工具链压缩包改存为 GitHub Release 的附件，也就是 sbwml 用 `openwrt_caches` 那种做法。

## Risks / Trade-offs

- **[BBRv3 在 6.18.y 升级时打不上]** 补丁改的是 TCP 核心，上游推进小版本时容易冲突。→ 补丁失败时 CI 立即停止；可以暂时退回上一个 lock，再重整补丁。
- **[BTF 增加体积和构建时间]** 目前只有估算：压缩后约 +1 MiB，常驻内存增加量相当。→ 第一次构建时实测 `Image` 大小；留意 `resolve_btfids` 的告警。
- **[LTO 导致个别包编译失败]** → 逐包退出并登记，不全局关闭。
- **[`-mcpu` 没能覆盖默认值]** → 用一个包的完整编译日志核对参数顺序；写进 toolchain 规格的测试场景。
- **[超过 GitHub 缓存 10 GB 上限]** → 退路见 D11。
- **[外接 SSD 经 virtiofs 的 IO 性能]** → 第一次完整构建时记录耗时；太慢就换到备选方案。
- **[启动脚本补丁影响其他 rockchip 设备]** 本项目只构建 R4S，可以接受。

## Migration Plan

- **首次交付**：这是全新项目，没有旧东西要迁移。第一次交付就是把单槽 SD 镜像刷进卡里启动。
- **回退**：在 A/B 那个 change 落地之前，回退方式就是重刷上一次的镜像。每次构建产物都会保留，以便回退。

## Open Questions

- 根分区的实际大小先按 1024 MiB，A/B 落地时会按 SD 卡的容量重新规划。这不影响本 change 的规格。
- zsh 两个插件具体固定到哪个版本，实施时取当时最新的稳定标签。
