# Tasks

## 1. 仓库骨架与构建环境

- [x] 1.1 建立仓库目录结构：`patches/{openwrt,packages,luci}`、`feed/`、`config/`、`files/`、`scripts/`、`docs/`、`.github/workflows/`。在 `.gitignore` 里排除构建目录。验证：`git status` 干净，目录都在。
- [x] 1.2 编写 `flake.nix`：用 `buildFHSEnv` 提供 OpenWrt 需要的宿主机依赖、`just`，以及固定版本的 clang/llvm（用于编译 BPF）。生成 `flake.lock`。验证：在 NixOS 虚拟机里 `nix flake check` 通过，`nix develop -c true` 退出码为 0。
- [x] 1.3 在 `justfile` 里加 `env-report` 命令，输出宿主机工具的版本清单。验证：这份清单在 11.3 里和 CI 的输出逐项比对。
- [x] 1.4 在 OrbStack 里创建 NixOS 虚拟机；在外接 SSD 上建 ext4 镜像文件，在虚拟机里 loop 挂载成 `WRT_WORKDIR`；把步骤写进 `docs/dev-setup.md`。验证：`findmnt $WRT_WORKDIR` 显示 ext4；在这个目录里建两个只有大小写不同的文件都能成功；macOS 系统盘的已用空间没有增长。
- [x] 1.5 写一个宿主机检查脚本，被所有会获取或编译源码的 `just` 命令先调用：不是 Linux 就立刻退出。验证：在 macOS 上执行 `just fetch`，返回非零并给出提示，也没有创建任何目录。
- [ ] 1.6 给 flake 增加 `nixpkgs-unstable` 输入，提供 `uv`、`qemu`、`dtc`、`u-boot-tools`；两种平台的 devShell 都加入 `shfmt`、`nixfmt`、`actionlint`、`editorconfig-checker`、`gitleaks`（design D10）。验证：`nix flake check` 通过；`just env-report` 输出 uv、qemu、shfmt、nixfmt、actionlint、editorconfig-checker、gitleaks 的版本。

## 2. 固定上游与补丁流程

- [x] 2.1 定义 `upstream.lock` 的格式：每个仓库记录 URL、SHA 和提交时间戳。初始值取 openwrt `1019293` 以及当时的 packages 和 luci 的 SHA，并写进 `docs/upstream-lock.md`。验证：lock 里的三个 SHA 都能在上游仓库解析到对应提交。
- [x] 2.2 实现 `scripts/fetch.sh`（对应 `just fetch`）：按 SHA 浅获取 openwrt；生成带 `^sha` 的 `feeds.conf`，外加自有 feed 的 `src-link`；写入 `version.date`；执行 `feeds update -a`。验证：换一台机器或换个时间执行两次，三个仓库检出的 SHA 都和 lock 一致；`feeds.conf` 里没有任何分支名。
- [x] 2.3 实现 `scripts/patch.sh`（对应 `just patch`）：按仓库、按文件名顺序执行 `git am`，并固定提交者的身份和时间；失败时先 `--abort` 再退出，并报出补丁文件名。验证：放一个故意冲突的补丁，命令返回非零并指出这个文件；删掉它再跑两次，得到的源码树 HEAD 的 SHA 完全相同。
- [x] 2.4 写一个检查脚本（对应 `just lint`），扫描 `scripts/`、`justfile` 和工作流，找远程下载后执行或打补丁的写法，以及对源码树的 `sed -i`。验证：当前仓库检查通过；往里临时加一行 `curl ... | sh`，检查失败。

## 3. 配置组合

- [x] 3.1 按 design D5 写出 `config/` 下的 `target`、`toolchain`、`kernel`、`rootfs`、`system`、`ci`、`dev` 这几个 seed 片段。验证：由 3.2 的校验覆盖。
- [x] 3.2 实现 `scripts/config.sh`（对应 `just config <profile>`）：拼接 seed，执行 `make defconfig`，逐行检查 seed 的每一行是否仍在 `.config` 里，最后输出 diffconfig 产物。验证：`dev` 和 `ci` 两个 profile 都通过；故意加一个不存在的选项时，校验失败并报出这一行。
- [ ] 3.3 让 `config.sh` 把 `config/kernel.config` 链接到 `$TREE/env/kernel-config`；在 `build.sh` 构建完成后逐行校验内核的 `.config`（design D7）。验证：叠加文件的每一行都出现在内核的 `.config` 里；故意在叠加文件中加一个不存在的符号，`build.sh` 失败并报出这一行。

## 4. 工具链与内核

- [ ] 4.1 F2FS 压缩改由内核配置叠加文件提供：在 `config/kernel.config` 写入 F2FS 压缩的五个选项，从 `kernel.seed` 删掉 `KERNEL_F2FS_*`，删除原来的补丁 0001（改为放在 `docs/upstream/`），BBRv3 和启动脚本的补丁顺延为 0001、0002。验证：内核 `.config` 里 `F2FS_FS_COMPRESSION`、`F2FS_FS_LZ4`、`F2FS_FS_ZSTD` 为 y，LZO 和 LZ4HC 为 not set；补丁队列只剩两个；连续执行两次 `just patch` 得到的 HEAD 相同。
- [x] 4.2 写 BBRv3 的补丁，把 sbwml 的 20 个补丁加进 `target/linux/generic/hack-6.18/`，第 0019 个也保留。验证：`make target/linux/prepare` 能干净地打上全部补丁；`tcp_bbr.ko` 编译成功，符号表里有 BBRv3 才有的 `bbr_skb_marked_lost` 和 `bbr_tso_segs`（OpenWrt 的 `MODULE_STRIPPED` 会去掉 `MODULE_VERSION`，所以不看版本号）。
- [x] 4.3 新增 `files/etc/sysctl.d/13-default-qdisc.conf`，写入 `net.core.default_qdisc=fq`。验证：由 10.2 的系统测试覆盖。
- [x] 4.4 核对编译参数：挑一个目标包用 `V=s` 编译。验证：日志里 `-O2 -mcpu=cortex-a72.cortex-a53+crypto` 排在 `-Os` 之后，交叉编译器的 GCC 主版本是 15。
- [ ] 4.5 用 `ci` profile 完整构建一遍。开 LTO 编不过的包，逐个在 `patches/packages` 里加 `no-lto` 退出，并登记到 `docs/lto-optouts.md`。验证：完整构建成功（由 11.2 的 `firmware` job 完成），登记表里的包和补丁队列一一对应。
- [ ] 4.6 在 `config/kernel.config` 加入 QEMU virt 平台驱动（PL011、`PCI_HOST_GENERIC`、virtio-pci/blk/net、i6300esb），用 `make listnewconfig` 把新出现的子选项全部写明取值。验证：内核 `.config` 里这些驱动都是 y；`listnewconfig` 的输出为空；把 `Image` 体积相比之前的增量记录在 `docs/kernel.md` 里。

## 5. 根文件系统与启动

- [x] 5.1 用 `rootfs.seed` 构建。验证：`bin/targets/rockchip/armv8/` 里只有 erofs 的 sysupgrade 镜像，没有 squashfs 或 ext4 的镜像。
- [x] 5.2 写启动脚本的补丁，在 bootargs 里追加 `fstools_overlay_compression_type=zstd`。验证：生成的 `boot.scr` 里有这个参数；`/overlay` 的挂载选项由 10.1 的系统测试覆盖。

## 6. 基础系统

- [x] 6.1 在自有 feed 里新增 `zsh-plugins` 包，把 autosuggestions 和 syntax-highlighting 固定到指定标签并校验哈希，同时提供全局 zshrc 来加载它们。验证：解开生成的 apk，两个插件和 zshrc 都在预期路径。
- [x] 6.2 新增 `files/etc/profile.d/99-zsh.sh`，只在交互式登录且 zsh 可执行时 `exec zsh -l`。验证：三种 shell 场景由 10.3 的系统测试覆盖。
- [ ] 6.3 新增一个 uci-defaults 脚本，只在 zram 的两个选项未设置时，写入 `zram_size_mb=1024` 和 `zram_comp_algo=zstd`。验证：由 10.3 的系统测试覆盖——全新安装后有 1 GiB、zstd 的 zram；把值改成 512 后做一次保留配置升级，值仍然是 512。
- [x] 6.4 实现镜像审计（对应 `just audit-image`），检查以下几项：不含 urngd、nginx、uwsgi、opkg、libpcre（PCRE1）、LRNG、shortcut-fe、natflow；没有带 UPX 标记的可执行文件；`/etc/shadow` 里 root 没有密码哈希；已装 luci 的 zh-cn 语言包。验证：对 5.1 产出的镜像运行，审计通过。
- [x] 6.5 镜像加入 bash（默认交互 shell 仍是 zsh），切换脚本只在 ash 登录时生效。验证：`just config dev` 的逐行校验通过；镜像审计显示 bash 已安装；`bash -l` 的场景由 10.3 的系统测试覆盖。

## 7. 代码规范

- [ ] 7.1 新增 `.editorconfig` 和 `.shellcheckrc`（启用 design D12 列出的可选检查），并修正现有代码中的全部告警。验证：`editorconfig-checker` 和 `shellcheck` 都通过。
- [ ] 7.2 把现有脚本按统一骨架重排并用 shfmt 格式化；把 `audit-image` 改名为 `image-audit`；新增 `workdir-unmount`，与 `workdir-mount` 成对；justfile 用 `[group(...)]` 分组，命令名与脚本名一致。验证：骨架检查通过；删掉任意一个脚本的 `set -eu` 后，骨架检查失败并指出这个脚本。
- [ ] 7.3 实现 `scripts/check.sh` 和 `scripts/fmt.sh`（对应 `just check` 和 `just fmt`），覆盖 shfmt、shellcheck、nixfmt、ruff format/check、ty、actionlint、editorconfig-checker、gitleaks、禁止模式检查和骨架检查，原来的 `just lint` 并入 `just check`。验证：在 macOS 和虚拟机上，先 `just fmt` 再 `just check` 都通过；`tests/quality/test_code_standards.py` 在仓库的临时副本里为每一种检查各制造一个违规，确认检查失败并指出位置。
- [ ] 7.4 编写 `docs/conventions.md`，写明全部规则、脚本骨架和命名规则。验证：文档里的每一条规则都能在 `check.sh` 中找到对应的检查，反之亦然。

## 8. 测试框架

- [ ] 8.1 建立 `tests/` 这个 uv 项目：`pyproject.toml`、`uv.lock`、`.python-version`（3.14）；依赖 pytest 和 labgrid；开发依赖 ruff 和 ty，配置按 design D12。验证：`uv sync --locked` 成功；`ruff check`、`ruff format --check` 和 `ty check` 都通过；修改依赖但不更新锁文件时，`uv sync --locked` 失败。
- [ ] 8.2 实现 `@spec` 和 `@target` 两种标记、`spec-coverage` 覆盖报告工具，以及 `verified-elsewhere.toml`；`spec-coverage` 同时检查目录规则（design D13）。验证：覆盖报告列出 foundation 的全部场景及其对应用例；标注一个不存在的场景时，检查失败并指出这个用例；`@spec` 标注的能力与所在模块不一致时，检查失败；在模拟器上运行时，仅真机的用例被跳过，并显示原因。
- [ ] 8.3 编写 labgrid 目标描述文件 `targets/emulation.yaml` 和 `targets/r4s.yaml`，以及 `just test` 和 `just test-device <host>`。验证：两个命令以 collect-only 方式收集到的用例 ID 集合相同。
- [ ] 8.4 编写 `tests/testing/test_harness.py`，在宿主上覆盖 testing/harness 规格中可自动化的场景：覆盖报告、指向不存在场景的标记、两种目标收集到相同的用例、跳过原因、锁文件与声明不一致、类型错误。“用例失败”场景由 11.6 验证，“在真机上运行”场景由 12.2 验证，两者登记在 `verified-elsewhere.toml`。验证：用例全部通过。

## 9. 模拟环境

- [ ] 9.1 实现出货产物的提取：解压镜像（容忍 fwtool 尾部数据）、从 FIT 中取出并解压 `Image`、从 `boot.scr` 生成启动参数（替换串口、用 MBR 签名算出 PARTUUID）；记录 sha256 并与 `manifest.json` 比对。验证：对本机构建的镜像运行提取，sha256 与构建清单一致；启动参数里有 `fstools_overlay_compression_type=zstd` 和正确的 `root=PARTUUID`。
- [ ] 9.2 生成 R4S 身份的设备树：用与启动时相同的参数导出 `virt` 的设备树，再用 `fdtput` 改写 `compatible` 和 `model`。验证：在模拟器中 `ubus call system board` 显示 `friendlyarm,nanopi-r4s`。
- [ ] 9.3 实现无 root 权限的网络沙箱：用户命名空间，`br-lan` 和 `br-wan` 两个网桥，`client-a` 和 `isp` 两个网络命名空间；拓扑以数据形式声明在 `wrt_tests/net.py` 里，后续 change 只增加条目。验证：以普通用户身份运行，`client-a` 通过 DHCP 拿到 10.0.0.0/24 的地址并能访问 10.0.0.1。OrbStack 虚拟机里已确认普通用户可以在用户命名空间中创建 veth、网桥和 tap；CI 依靠 `prepare-runner.sh` 里的 AppArmor 设置，所以不需要 sudo 的退路。
- [ ] 9.4 实现故障注入：每个用例用 qcow2 覆盖层还原磁盘、强制断电并从同一块磁盘重启、提供 i6300esb 看门狗、在启动过程中向串口输入按键。验证：`tests/testing/test_emulation.py` 覆盖 testing/emulation 规格的全部场景，并且都通过。

## 10. 系统测试用例（每个规格能力一个模块）

- [ ] 10.1 `tests/firmware/test_rootfs.py`：`/rom` 是 erofs；`/overlay` 是 f2fs 并带 zstd；恢复出厂只清空 overlay，EROFS 不变；镜像能直接启动。验证：在模拟器中全部通过。
- [ ] 10.2 `tests/firmware/test_kernel.py`：内核版本、BTF、只有 cgroup2、tcx 程序能加载、文件系统不需要模块、BBRv3 的回调和 sysctl 以及 `ss -ti`、virt 驱动。另外做 kmod 兼容性测试：从同一次构建的仓库安装一个 kmod 能成功加载；用 apk 生成一个依赖不同内核版本标识的测试包，安装会被拒绝。验证：在模拟器中全部通过。
- [ ] 10.3 `tests/firmware/test_base_system.py`：LAN 地址（全新安装、保留配置升级、故障安全模式）；LuCI 由 uhttpd 以中文界面提供；镜像里没有 nginx 和 uwsgi；四种 shell 场景；zram（覆盖 6.3 的两种情况）；没有预置密码；不包含的组件。验证：在模拟器中全部通过。
- [ ] 10.4 把 `docs/validation/foundation.md` 里原来的人工核对清单改为指向自动化用例，只保留“仅真机”的项目。验证：`spec-coverage` 报告中 foundation 没有未覆盖的场景；build 域和 firmware/toolchain 的场景都登记在 `verified-elsewhere.toml`，指向 CI 里验证它们的 job。

## 11. CI

- [ ] 11.1 编写 `host-toolchain` job：安装 Nix，准备 runner，按 design D11 计算缓存键；缓存未命中时构建 tools 和工具链，只打包实际存在的路径并保存。验证：冷缓存运行在 6 小时内完成，并把各阶段耗时记录到 `docs/ci.md`；第二次运行缓存命中，几分钟内结束。
- [ ] 11.2 编写 `firmware` job：恢复工具链时刷新文件时间戳，恢复 ccache 和 dl 缓存；用 `ci` profile 构建；生成 `manifest.json`；上传未签名的产物。验证：job 在 6 小时内完成；清单里的 vermagic 和镜像里 `kmod-*` 依赖的内核版本标识一致。
- [ ] 11.3 核对环境和权限。验证：CI 里 `just env-report` 的输出和本机的完全一致；工作流里没有引用任何密钥；在一个没有配置任何密钥的 fork 里运行成功。
- [ ] 11.4 检查缓存用量。验证：工具链缓存和 ccache 的总大小记录进 `docs/ci.md`；如果超过 10 GB，按 design D11 把工具链改存为 Release 附件，并确认下一次运行能正确恢复。
- [ ] 11.5 把规范检查拆成独立的 `check.yml`，在每次推送时运行 `just check`，不做路径过滤。验证：只改文档的推送只触发 `check.yml`，不触发 `build.yml`；故意引入一处格式问题后推送，`check` 失败。
- [ ] 11.6 在 `build.yml` 里增加 `system-test` job：依赖 `firmware` 的产物，运行 `just test` 并发布 JUnit 报告。验证：job 在 30 分钟内完成；人为让一个用例失败后，job 失败，并且报告里有这个用例。

## 12. 真机冒烟与上游贡献

- [ ] 12.1 把只能在真机上验证的项目写成 `@target("device")` 用例：U-Boot 从 SD 卡启动、两个物理网口的驱动和中断亲和性、吞吐与温度基线（不作为门槛）。验证：在模拟器上运行时，这些用例被跳过并显示原因。
- [ ] 12.2 把模拟测试通过的镜像刷进 SD 卡，在 R4S 上运行 `just test-device <host>`。验证：报告全部通过（包括仅真机的用例），结果存档到 `docs/validation/foundation-device.md`。这是本 change 里唯一需要真机的步骤。
- [ ] 12.3 在 `docs/upstream/` 准备好两个上游补丁：一个是 EROFS 压缩算法选择项，另一个是 F2FS 压缩的 `KERNEL_*` 选项。它们只在本地准备，提交前必须得到维护者的明确同意。验证：两个补丁都能用 `git am` 干净地打到 lock 所固定的上游提交上；`docs/upstream-contributions.md` 记录了两者的状态。
