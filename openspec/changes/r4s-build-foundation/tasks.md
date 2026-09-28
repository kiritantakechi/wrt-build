# Tasks

## 1. 仓库骨架与构建环境

- [x] 1.1 建立仓库目录结构：`patches/{openwrt,packages,luci}`、`feed/`、`config/`、`files/`、`scripts/`、`docs/`、`.github/workflows/`。在 `.gitignore` 里排除构建目录。验证：`git status` 干净，目录都在。
- [x] 1.2 编写 `flake.nix`：用 `buildFHSEnv` 提供 OpenWrt 需要的宿主机依赖、`just`，以及固定版本的 clang/llvm（用于编译 BPF）。生成 `flake.lock`。验证：在 NixOS 虚拟机里 `nix flake check` 通过，`nix develop -c true` 退出码为 0。
- [x] 1.3 在 `justfile` 里加 `env-report` 命令，输出宿主机工具的版本清单。验证：这份清单会在 7.3 里和 CI 的输出逐项比对。
- [x] 1.4 在 OrbStack 里创建 NixOS 虚拟机；在外接 SSD 上建 ext4 镜像文件，在虚拟机里 loop 挂载成 `WRT_WORKDIR`；把步骤写进 `docs/dev-setup.md`。验证：`findmnt $WRT_WORKDIR` 显示 ext4；在这个目录里建两个只有大小写不同的文件都能成功；macOS 系统盘的已用空间没有增长。
- [x] 1.5 写一个宿主机检查脚本，被所有会获取或编译源码的 `just` 命令先调用：不是 Linux 就立刻退出。验证：在 macOS 上执行 `just fetch`，返回非零并给出提示，也没有创建任何目录。

## 2. 固定上游与补丁流程

- [x] 2.1 定义 `upstream.lock` 的格式：每个仓库记录 URL、SHA 和提交时间戳。初始值取 openwrt `1019293` 以及当时的 packages 和 luci 的 SHA，并写进 `docs/upstream-lock.md`。验证：lock 里的三个 SHA 都能在上游仓库解析到对应提交。
- [x] 2.2 实现 `scripts/fetch.sh`（对应 `just fetch`）：按 SHA 浅获取 openwrt；生成带 `^sha` 的 `feeds.conf`，外加自有 feed 的 `src-link`；写入 `version.date`；执行 `feeds update -a`。验证：换一台机器或换个时间执行两次，三个仓库检出的 SHA 都和 lock 一致；`feeds.conf` 里没有任何分支名。
- [x] 2.3 实现 `scripts/patch.sh`（对应 `just patch`）：按仓库、按文件名顺序执行 `git am`，并固定提交者的身份和时间；失败时先 `--abort` 再退出，并报出补丁文件名。验证：放一个故意冲突的补丁，命令返回非零并指出这个文件；删掉它再跑两次，得到的源码树 HEAD 的 SHA 完全相同。
- [x] 2.4 写一个检查脚本（对应 `just lint`），扫描 `scripts/`、`justfile` 和工作流，找远程下载后执行或打补丁的写法，以及对源码树的 `sed -i`。验证：当前仓库检查通过；往里临时加一行 `curl ... | sh`，检查失败。

## 3. 配置组合

- [x] 3.1 按 design D5 写出 `config/` 下的 `target`、`toolchain`、`kernel`、`rootfs`、`system`、`ci`、`dev` 这几个 seed 片段。验证：由 3.2 的校验覆盖。
- [x] 3.2 实现 `scripts/config.sh`（对应 `just config <profile>`）：拼接 seed，执行 `make defconfig`，逐行检查 seed 的每一行是否仍在 `.config` 里，最后输出 diffconfig 产物。验证：`dev` 和 `ci` 两个 profile 都通过；故意加一个不存在的选项时，校验失败并报出这一行。

## 4. 工具链与内核补丁

- [x] 4.1 写补丁 `patches/openwrt/0001-config-kernel-add-F2FS-compression-options.patch`，在 `config/Config-kernel.in` 里加入 `KERNEL_F2FS_FS_COMPRESSION`、`KERNEL_F2FS_FS_ZSTD` 和 `KERNEL_F2FS_FS_LZ4`。验证：生成的内核 `.config` 里有 `CONFIG_F2FS_FS_COMPRESSION=y` 和 `CONFIG_F2FS_FS_ZSTD=y`。
- [x] 4.2 写补丁 `patches/openwrt/0002-generic-add-BBRv3-for-6.18.patch`，把 sbwml 的 20 个 BBRv3 补丁加进 `target/linux/generic/hack-6.18/`，第 0019 个也保留。验证：`make target/linux/prepare` 能干净地打上全部补丁；`tcp_bbr.ko` 编译成功，符号表里有 BBRv3 才有的 `bbr_skb_marked_lost` 和 `bbr_tso_segs`（OpenWrt 的 `MODULE_STRIPPED` 会去掉 `MODULE_VERSION`，所以不看版本号）。
- [x] 4.3 新增 `files/etc/sysctl.d/13-default-qdisc.conf`，写入 `net.core.default_qdisc=fq`。验证：设备启动后，`sysctl net.core.default_qdisc` 输出 fq。这一步在 8.1 统一上机核对。
- [x] 4.4 核对编译参数：挑一个目标包用 `V=s` 编译。验证：日志里 `-O2 -mcpu=cortex-a72.cortex-a53+crypto` 排在 `-Os` 之后，交叉编译器的 GCC 主版本是 15。
- [ ] 4.5 用 `ci` profile 完整构建一遍。开 LTO 编不过的包，逐个在 `patches/packages` 里加 `no-lto` 退出，并登记到 `docs/lto-optouts.md`。验证：完整构建成功，登记表里的包和补丁队列一一对应。

## 5. 根文件系统与启动

- [x] 5.1 用 `rootfs.seed` 构建。验证：`bin/targets/rockchip/armv8/` 里只有 erofs 的 sysupgrade 镜像，没有 squashfs 或 ext4 的镜像。
- [x] 5.2 写补丁 `patches/openwrt/0003-rockchip-bootscript-enable-f2fs-zstd-overlay.patch`，在 bootargs 里追加 `fstools_overlay_compression_type=zstd`。验证：生成的 `boot.scr` 里有这个参数；上机后在 8.1 核对 `/overlay` 的挂载选项。

## 6. 基础系统

- [x] 6.1 在自有 feed 里新增 `zsh-plugins` 包，把 autosuggestions 和 syntax-highlighting 固定到指定标签并校验哈希，同时提供全局 zshrc 来加载它们。验证：解开生成的 apk，两个插件和 zshrc 都在预期路径。
- [x] 6.2 新增 `files/etc/profile.d/99-zsh.sh`，只在交互式登录且 zsh 可执行时 `exec zsh -l`。验证：上机在 8.1 核对三种情况——SSH 交互登录进 zsh；`ssh host cmd` 由 ash 执行；把 zsh 挪走之后仍能登录进 ash。
- [ ] 6.3 新增一个 uci-defaults 脚本，只在 zram 的两个选项未设置时，写入 `zram_size_mb=1024` 和 `zram_comp_algo=zstd`。验证：全新安装后 `swapon` 显示 1 GiB 的 zram；手动改成 512 后做一次保留配置升级，值仍然是 512。
- [x] 6.4 实现镜像审计（对应 `just audit-image`），检查以下几项：不含 urngd、nginx、uwsgi、opkg、libpcre（PCRE1）、LRNG、shortcut-fe、natflow；没有带 UPX 标记的可执行文件；`/etc/shadow` 里 root 没有密码哈希；已装 luci 的 zh-cn 语言包。验证：对 5.1 产出的镜像运行，审计通过。

## 7. CI

- [ ] 7.1 编写 `host-toolchain` job：安装 Nix，清理磁盘，按 design D11 计算缓存键；缓存未命中时构建 tools、toolchain 和宿主软件包，再保存压缩包。验证：冷缓存运行在 6 小时内完成，并把各阶段耗时记录到 `docs/ci.md`；第二次运行缓存命中，几分钟内结束。
- [ ] 7.2 编写 `firmware` job：恢复工具链时刷新文件时间戳，恢复 ccache 和 dl 缓存；用 `ci` profile 构建；生成 `manifest.json`；上传未签名的产物。验证：job 在 6 小时内完成；清单里的 vermagic 和镜像里 `kmod-*` 依赖的内核版本标识一致。
- [ ] 7.3 核对环境和权限。验证：CI 里 `just env-report` 的输出和本机 1.3 的完全一致；工作流里没有引用任何密钥；在一个没有配置任何密钥的 fork 里运行成功。
- [ ] 7.4 检查缓存用量。验证：工具链缓存和 ccache 的总大小记录进 `docs/ci.md`；如果超过 10 GB，按 design D11 把工具链改存为 Release 附件，并确认下一次运行能正确恢复。

## 8. 上机验证与上游贡献

- [ ] 8.1 把单槽镜像写入 microSD 卡，在 R4S 上启动，逐条核对以下规格场景：`/rom` 是 erofs；`/overlay` 是 f2fs 且带 zstd；LAN 是 10.0.0.1；故障安全模式可以访问；LuCI 为简体中文；`/sys/kernel/btf/vmlinux` 存在；只有 cgroup2；BBR 和 fq 生效，`/proc/kallsyms` 里有 BBRv3 的回调；有 1 GiB 的 zram；恢复出厂只清空 overlay；三种 shell 场景。验证：每条场景的结果记录在 `docs/validation/foundation.md`，全部通过。
- [ ] 8.2 kmod 兼容性测试。验证：在设备上安装同一次构建产出的任意一个 kmod，能成功加载；改一处内核配置另外构建一次，拿它产出的 kmod 来装，apk 会拒绝。
- [ ] 8.3 （提交前必须得到你的明确同意）向上游 openwrt 提交 `include/image.mk:110` 的修正（`docs/upstream/0001-build-make-the-EROFS-compression-selectable.patch`）。不能只把 `CONFIG_EROFS_FS_ZIP_LZMA` 改名为 `CONFIG_KERNEL_EROFS_FS_ZIP_LZMA`：后者没有提示项、开启 EROFS 时默认为 y，只改名会让所有 EROFS 构建静默改用 LZMA。补丁改为新增一个压缩算法的选择项，默认 lz4hc。验证：PR 链接记录在 `docs/upstream-contributions.md`。
