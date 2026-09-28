# Design

## Context

动机见 proposal.md 的 Why 一节。本设计依赖以下现状和约束。

### 上游（main `1019293`，2026-09-27，均已在源码中核对）

- rockchip 默认内核是 6.18.52；U-Boot 2026.07、TF-A 2.15.0、erofs-utils 1.9.4、apk 3.0.5、musl 1.2.6。
- GCC 默认是 14，15 可选；llvm-bpf 22.1.3，dwarves 1.31。
- `friendlyarm_nanopi-r4s` 就是 “4GB LPDDR4” 这个型号（`target/linux/rockchip/image/armv8.mk:139-145`）。
- `LINUX_KCONFIG_LIST` 的最后一层是 `$(TOPDIR)/env/kernel-config`（`include/target.mk:173`），这是上游原生支持的内核配置叠加文件，而且 `/env` 已在上游的 `.gitignore` 里。
- `.config` 里的 `CONFIG_KERNEL_*` 只会写进内核配置里那些在 Kconfig 中有定义的符号（`include/kernel-defaults.mk:118-119`）。
- 内核配置遇到没有取值的新符号时，构建会停下来报错。这在打开 F2FS 压缩时已经实际遇到过，要用 `make listnewconfig` 把所有缺值的符号一次性找出来。
- OpenWrt 开启了 `CONFIG_MODULE_STRIPPED`，模块里的 `MODULE_VERSION` 等信息都会被删掉。

### 宿主机与 Nix 环境（实施时核对）

- **宿主机**：M1 Max、32 GB 内存；OrbStack 的 NixOS 25.11 虚拟机（aarch64，9 核、15 GB），虚拟机里没有 `/dev/kvm`。
- **外接 SSD**：HFS+，实测顺序写入约 75 MB/s。
- **必须在 Linux 上构建**：`KERNEL_DEBUG_INFO_BTF` 和 mold 都依赖 `!HOST_OS_MACOS`，dwarves 在 Darwin 上会被跳过。
- **FHS 环境里需要补齐的三件事**：
  1. `/usr/include` 里要有 glibc 头文件，否则 CMake 的 `find_path` 找不到 `iconv.h`。
  2. 要有能处理 LTO 的归档工具 `gcc-ar`，宿主机版 apk 用 `b_lto` 链接静态库时离不开它。
  3. 要设置 `FAKEROOTDONTTRYCHOWN=1`：在用户命名空间里，真实的 `chown` 返回的是 EINVAL，而 fakeroot 只会忽略 EPERM，于是报错。
- **Ubuntu 24.04 runner** 用 AppArmor 限制了非特权用户命名空间，bubblewrap 需要先放开这个限制。

### GitHub 托管 runner

- 单个 job 最长 6 小时；标准 Linux runner 是 4 核、16 GB；缓存总共 10 GB。
- 冷缓存实测：tools 约 43 分钟，GCC 15 工具链约 35 分钟。

## Goals / Non-Goals

**Goals:**
- 同一份 lock，本机和 CI 得到完全相同的源码树、配置和构建时间戳。
- 产出一个单槽 SD 镜像，以及出自同一次构建的全量 kmod 仓库。
- 规格场景尽量都在模拟器中对出货镜像自动验证；真机只剩一条命令，外加少数几项硬件专属检查。
- 代码规范可以机器检查，并在 CI 中强制执行。

**Non-Goals:**
- 不在本 change 做：A/B（`r4s-ab-rollback`）、数据面（`r4s-ebpf-datapath`）、服务（`r4s-services`）、签名与发布（`r4s-release-pipeline`）。
- 不用 `-mcpu` 去调优内核本身，也不涉及硬件卸载。
- 不在模拟器里测性能。在 TCG 下测出来的吞吐没有参考意义。

## Decisions

### D1. 仓库布局

```
wrt-build/
  flake.nix  flake.lock           host environment (build FHS + tooling)
  justfile                        entry points, grouped: build / test / quality / workdir
  upstream.lock                   openwrt / packages / luci: url, sha, commit epoch
  patches/<repo>/*.patch          git format-patch series, applied with git am
  feed/                           own packages (src-link)
  config/*.seed                   package/diffconfig fragments
  config/kernel.config            kernel symbols not exposed as CONFIG_KERNEL_*
  config/profiles                 profile -> seed list
  files/                          rootfs overlay
  scripts/*.sh                    POSIX sh, one skeleton (D12)
  tests/                          pytest + labgrid project (uv), see D13
  .editorconfig .shellcheckrc     style configuration
  .github/workflows/{check,build}.yml
  docs/

$WRT_WORKDIR/  (outside repo)     openwrt/  dl/  ccache/  out/<profile>/  emu/
```

### D2. 按 SHA 获取上游

- **做法**：openwrt 用 `git fetch --depth 1 origin <sha>` 获取。每个 feed 也由 `fetch.sh` 自己按 SHA 浅获取。
- **为什么不让 `scripts/feeds update` 去取 feed**：feed 目录已经存在、并且带 `^sha` 时，它会直接跳过，lock 里的 SHA 改了也不会跟着更新。所以取完之后只执行 `feeds update -i` 重建索引。
- **`feeds.conf`**：每个 feed 写成 `src-git <name> <url>^<sha>`，另加一行自有 feed 的 `src-link`。

### D3. 补丁用 git am 应用，提交时间和身份都固定

- 每次先把各仓库重置回 lock 里的提交，并执行 `git clean -fd` 清掉上一次补丁新增的文件。
- 然后执行 `git am --committer-date-is-author-date`，提交者身份也固定下来。这样同一组补丁无论什么时候应用，得到的 HEAD 都相同。
- 任何一个补丁失败，就执行 `--abort`，并报出这个补丁的文件名。

### D4. 构建时间戳取自 lock

`upstream.lock` 里 openwrt 那一行的时间戳被写入 `version.date`，`scripts/get_source_date_epoch.sh` 会优先读取它。

### D5. 软件包配置：seed 片段 + defconfig + 逐行校验

- **组合方式**：`config/profiles` 定义每个 profile 由哪些 seed 片段组成，按顺序拼接后执行 `make defconfig`。
- **校验**：seed 里的每一行（包括 `# ... is not set`）都必须原样出现在最终的 `.config` 中，否则失败。最后输出 diffconfig。
- **各个 seed 的内容**：见仓库中的 `config/*.seed`。几个要点：
  - `IMAGEOPT` 和 `PREINITOPT` 必须显式打开，否则自定义的 `TARGET_PREINIT_IP` 会被 defconfig 静默丢弃。
  - zram 的 zstd 需要打开 `KERNEL_ZRAM_BACKEND_ZSTD` 和 `KERNEL_ZRAM_DEF_COMP_ZSTD`。

### D6. 工具链只靠配置

`CONFIG_EXTRA_OPTIMIZATION` 排在 `TARGET_OPTIMIZATION` 之后（`rules.mk:256`），所以 `-O2 -mcpu=cortex-a72.cortex-a53+crypto` 会覆盖默认值。实测命令行为 `-Os -pipe -mcpu=generic ... -O2 -mcpu=cortex-a72.cortex-a53+crypto`。

个别包在 LTO 下编不过时，只让这个包退出 LTO：在 `patches/packages` 里用补丁给它加上 `PKG_BUILD_FLAGS:=no-lto`，并在 `docs/lto-optouts.md` 里登记。

### D7. 内核：两个补丁，加一个叠加配置

1. **BBRv3**（`patches/openwrt/0001`）：20 个补丁放进 `hack-6.18/960-bbr3-*`，全部保留。
   - 第 0019 个改的是通用的 `bpf_tcp_ca.c`，缺了它就编译不过。
   - 继续用上游的 `kmod-tcp-bbr` 打包。
   - 因为 `MODULE_STRIPPED` 会删掉版本号，验证方式是核对 BBRv3 才有的回调：`bbr_skb_marked_lost` 和 `bbr_tso_segs`。
2. **启动脚本**（`patches/openwrt/0002`）：在 `default.bootscript` 里加上 `fstools_overlay_compression_type=zstd`。
3. **内核配置叠加文件** `config/kernel.config`：`config.sh` 把它链接到 `$TREE/env/kernel-config`，内容分为两组：

```
# f2fs overlay compression (fstools_overlay_compression_type=zstd)
CONFIG_F2FS_FS_COMPRESSION=y
# CONFIG_F2FS_FS_LZO is not set
CONFIG_F2FS_FS_LZ4=y
# CONFIG_F2FS_FS_LZ4HC is not set
CONFIG_F2FS_FS_ZSTD=y

# QEMU virt guest: the shipped kernel boots unchanged in emulation (D14)
CONFIG_PCI_HOST_GENERIC=y
CONFIG_SERIAL_AMBA_PL011=y
CONFIG_SERIAL_AMBA_PL011_CONSOLE=y
CONFIG_VIRTIO_PCI=y
CONFIG_VIRTIO_BLK=y
CONFIG_VIRTIO_NET=y
CONFIG_I6300ESB_WDT=y
# plus every symbol `make listnewconfig` reports for these, with explicit values
```

- **为什么删掉原来的补丁 0001**：它给 `Config-kernel.in` 加 F2FS 选项。叠加文件是上游原生支持的机制，不需要补丁，也不会随上游改动而打不上。那个补丁作为上游贡献只在本地准备，不再放进补丁队列。
- **构建后校验**：`build.sh` 在构建完成后核对，叠加文件中的每一行都必须出现在内核的 `.config` 里，否则失败。
- **seed 里保留 `CONFIG_KERNEL_*` 的选项**（BTF、`BPF_EVENTS`、cgroup 等）：这些选项会影响软件包依赖和宿主机工具的选择，所以它们留在 seed 里。
- **备选方案**：给 `Config-kernel.in` 补上全部选项，或者直接修改 `target/.../config-6.18`。都否决：前者补丁越打越多，后者跟着上游一改就打不上。

### D8. 基础系统

- **LAN 地址**：通过 `TARGET_PREINIT_IP` 加 `DEFAULT_LAN_IP_FROM_PREINIT` 设置，它会生成 `board.d/99-lan-ip`，只在生成默认配置时生效，所以保留配置升级时不会覆盖用户的地址。
- **zram**：用 uci-defaults 脚本写入 1024 MiB 和 zstd，只在这两项尚未设置时才写。
- **LuCI**：由 uhttpd 通过 ucode CGI（`/www/cgi-bin/luci`）提供。`uhttpd-mod-ucode` 只是进程内加速，不是必需的。
- **shell**：
  - 登录 shell 是 ash；`profile.d/99-zsh.sh` 只在从 ash 交互登录时 `exec zsh -l`，`bash -l` 不会被切走。
  - zsh 插件的测试数据不打进包里。

### D9. 本机构建目录

外接 SSD 上放一个 112 GiB 的 ext4 镜像文件，在虚拟机里 loop 挂载到 `/mnt/wrt`。`workdir-mount` 和 `workdir-unmount` 成对提供，`mount` 可以重复执行，`--format` 只会格式化空镜像。

### D10. 构建环境（flake）

- **两个 nixpkgs 输入，各管一摊**：
  - `nixpkgs`（nixos-25.11）只用来构建 FHS 环境，求稳。
  - `nixpkgs-unstable` 只用来提供最新的 `uv`，以及模拟器相关的 `qemu`、`dtc`、`u-boot-tools`，求新。
- **Python 相关工具由 uv 管理**：ruff、ty、pytest、labgrid 以及 Python 解释器本身都由 `tests/uv.lock` 固定版本，不走 Nix。
- **测试工具组**：flake 里的 `testTools` 列表收纳模拟环境中各类对端要用的守护进程和客户端，例如后续 change 加入的 PPPoE 服务端和镜像仓库。它们来自 `nixpkgs`，放进 FHS 环境，`just test` 也在 FHS 里运行。foundation 只放 `iproute2`、`dnsmasq` 和 `curl`，满足 `client-a` 用 DHCP 取地址和访问 LuCI。
- **FHS 的 profile 里导出的变量**：
  - `NIX_HARDENING_ENABLE=`
  - `AR=gcc-ar`、`NM=gcc-nm`、`RANLIB=gcc-ranlib`
  - `FAKEROOTDONTTRYCHOWN=1`
  - `WRT_FHS=1`

### D11. CI：两个工作流，四个 job

```
check.yml   (every push/PR, no paths filter)          ~2 min
  check: nix develop -c just check

build.yml   (paths-ignore: openspec/**, docs/**, **/*.md)
  host-toolchain  key = hash(arch, tools/, toolchain/, lang/golang, lang/rust,
                             toolchain.seed, flake.nix, flake.lock)
                  miss -> build tools + toolchain -> pack existing paths only
  firmware        needs host-toolchain; unpack + touch; dl/ccache caches;
                  ci profile (ALL_KMODS); manifest.json; unsigned artifacts
  system-test     needs firmware; just test (emulation, TCG); JUnit report
```

- **为什么单独拆出 `check.yml`**：它不受路径过滤的限制，任何推送都会触发，而且很快就能出结果；重构建则只在代码变化时才跑。
- **缓存放不下怎么办**：缓存用量超过 10 GB 时，把工具链压缩包改为 Release 附件存放。

### D12. 代码规范

| 对象 | 格式化 | 静态检查 |
|---|---|---|
| shell | `shfmt`（按 `.editorconfig`：POSIX 方言、tab 缩进、`switch_case_indent`） | `shellcheck`（`.shellcheckrc`：`shell=sh`，启用 `add-default-case`、`avoid-nullary-conditions`、`check-extra-masked-returns`、`check-set-e-suppressed`、`check-unassigned-uppercase`、`deprecate-which`、`quote-safe-variables`、`require-variable-braces`） |
| Nix | `nixfmt` | — |
| Python | `ruff format` | `ruff check`（`select = ["ALL"]`，排除项写在 pyproject 里并注明原因）、`ty check`（全部规则按 error 处理） |
| workflows | — | `actionlint` |
| 全部文本 | `.editorconfig`（UTF-8、LF、文件末尾换行、去掉行尾空格） | `editorconfig-checker`（`patches/` 除外） |
| 仓库 | — | 禁止模式检查（远程下载后执行或打补丁、就地 `sed -i`）、脚本骨架检查、`gitleaks`（全部历史里不能有密钥） |

- **脚本骨架**：每个脚本按下面的顺序组织，骨架检查会核对前三部分。

```sh
#!/bin/sh
# <object>-<verb>: one-line purpose.
# Usage: scripts/<name>.sh [args]
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

<argument parsing>
require_linux; require_workdir; ensure_fhs "$@"   # only the guards the script needs
<main>
```

- **命名规则**：
  - 流水线阶段是单独的动词：`fetch`、`patch`、`config`、`build`、`test`、`check`、`fmt`。
  - 针对具体对象的操作用“对象-动词”：`workdir-mount`/`workdir-unmount`、`toolchain-key`/`toolchain-build`/`toolchain-pack`/`toolchain-unpack`、`image-audit`、`env-report`。
  - just 命令名和脚本名一致，并用 `[group(...)]` 分组。
  - 环境变量统一用 `WRT_` 前缀。
- **一条命令检查**：`just check` 只检查、不修改；`just fmt` 执行格式化。两者都能在 macOS 上运行，所用工具由对应平台的 devShell 提供。

### D13. 测试框架

```
tests/
  pyproject.toml  uv.lock  .python-version     (python 3.14, uv-managed)
  conftest.py                                  fixtures: shell, ssh, emulator, net
  targets/emulation.yaml  targets/r4s.yaml     labgrid environments (symmetric)
  wrt_tests/                                   helpers: spec markers, coverage, emu, net
  <domain>/test_<capability>.py                one module per spec capability, e.g.
      firmware/test_rootfs.py      <-> specs/firmware/rootfs
      testing/test_emulation.py    <-> specs/testing/emulation
  unit/test_<helper>.py                        unit tests of wrt_tests/, no target, no @spec
```

- **目录规则**：
  - 规格用例只能放在 `tests/<域>/test_<能力>.py`，能力名里的连字符换成下划线；模块里的每个用例都必须带 `@spec`，而且标注的能力必须就是这个模块对应的能力。
  - `tests/unit/` 只测 `wrt_tests/` 里的辅助代码，不连接任何目标，也不带 `@spec`。
  - 两条规则都由 `spec-coverage` 检查，没有例外。

- **与规格的对应**：
  - 每个用例用 `@spec("firmware/rootfs", "<requirement>", "<scenario>")` 标注它对应的场景。
  - `uv run spec-coverage` 解析 `openspec/` 下的规格和收集到的用例，报告哪些场景没有用例。
  - 由构建或 CI 本身验证的场景（例如 build/ci）记录在 `tests/verified-elsewhere.toml` 里，并写明由谁验证。
- **目标选择**：
  - 用例用 `@target("emulation")` 或 `@target("device")` 标注专属目标，并写明原因。没有标注的用例在两种目标上都运行。
  - `just test` 用 `emulation.yaml`；`just test-device <host>` 用 `r4s.yaml`。
  - 真机的电源控制用 labgrid 的 `ManualPowerDriver`，需要断电时提示人工操作。
- **报告**：两种目标都输出 JUnit 和终端摘要，格式相同。

### D14. 模拟环境

```
sysupgrade.img.gz --gunzip (fwtool trailer tolerated)--> disk.raw (read-only base)
   per test: qcow2 overlay on disk.raw  (reset between tests, keep across a power cut)
   p1: kernel.img (FIT) --dumpimage--> Image.lzma --unlzma--> Image
       boot.scr --> bootargs template: ${serial_port}->ttyAMA0, earlycon dropped,
                    ${uuid}-> PARTUUID of p2 from the MBR signature
qemu -machine virt,gic-version=3,dumpdtb=virt.dtb  (same args)  --fdtput-->
       / compatible = "friendlyarm,nanopi-r4s", model = "FriendlyElec NanoPi R4S"

qemu-system-aarch64 -machine virt,gic-version=3 -cpu cortex-a72 -smp 6 -m 4G
  -kernel Image -dtb r4s.dtb -append "<bootargs>"
  -drive if=none,id=d0,file=overlay.qcow2 -device virtio-blk-pci,drive=d0
  -netdev tap,id=wan,ifname=emu-wan -device virtio-net-pci,netdev=wan   # eth0 = WAN
  -netdev tap,id=lan,ifname=emu-lan -device virtio-net-pci,netdev=lan   # eth1 = LAN
  -device i6300esb -action watchdog=reset  -serial <labgrid console>

sandbox: unshare --user --map-root-user --net --mount (rootless)
  br-lan: emu-lan + host side 10.0.0.2 (test runner) + veth -> netns "client-a"
  br-wan: emu-wan + veth -> netns "isp"   (later changes run PPPoE/DHCPv6/STUN here)
```

- **为什么要伪装成 R4S 的板型**：R4S 的 `02_network` 按 `eth1` 为 LAN、`eth0` 为 WAN 分配网口角色，板型的升级元数据校验也依赖它。改了 `compatible` 之后，这些都走与真机相同的代码。LED 这类硬件节点在模拟器里不存在，相关脚本只会记一条日志，不影响功能。
- **为什么用 TCG**：本机虚拟机没有 KVM，CI 上又是 x86 模拟 aarch64，只能用 TCG。启动一次大约一两分钟，每个测试模块只启动一次，用例之间用快照还原磁盘。
- **在 FHS 环境里运行测试**：uv 管理的 Python 和 manylinux wheel 在 NixOS 上需要 FHS 才能运行，所以测试也在 FHS 环境里跑；网络沙箱是嵌套在里面的用户命名空间。
- **模拟器覆盖不了、只能留给真机的**：
  - RK3399 的 BootROM、TPL/SPL 和 U-Boot 从 SD 卡启动；
  - 两个物理网口的驱动（stmmac、r8169）以及中断亲和性；
  - DesignWare 看门狗的真实复位；
  - USB3 UAS；
  - 吞吐和温度。

  这些都以 `@target("device")` 用例的形式存在。

## Risks / Trade-offs

- **[BBRv3 在 6.18.y 升级时打不上]** 补丁失败时 CI 立即停止；可以暂时退回上一个 lock，再重整补丁。
- **[virt 驱动增加内核体积]** 预计约 100～300 KB，实施时实测。R4S 上没有对应的设备，这些驱动不会被探测到。
- **[叠加文件漏写子选项，导致内核配置卡住]** 实施时用 `listnewconfig` 补全；构建后的逐行校验会拦住配置漂移。
- **[模拟器与真机的差异被误认为已覆盖]** 覆盖报告把只能在真机上验证的场景单独列出；板型身份一致，但硬件节点不同，这一点写在文档里。
- **[嵌套用户命名空间不可用]** 本机和 CI 都实测一遍；如果不可用，退回到用 sudo 建立网络命名空间（CI runner 和虚拟机都有 root 权限）。
- **[ty 仍处于 0.0.x 阶段]** 版本由 `uv.lock` 固定；升级 ty 放在每周 bump 里一起处理，出现误报时在 pyproject 里记录下来。
- **[TCG 速度慢]** 每个模块只启动一次虚拟机，用例之间用快照还原；`system-test` job 的目标耗时是 30 分钟以内。
- **[超过 GitHub 缓存上限]** 退路见 D11。

## Migration Plan

- **新项目**：这是全新项目，没有旧东西要迁移。第一次交付就是一个通过了模拟测试的单槽镜像。
- **已实施的部分需要这样调整**：
  - 删除补丁 0001，F2FS 选项改由叠加文件提供，BBRv3 和启动脚本的补丁顺延为 0001、0002；
  - 已有的脚本按统一骨架重排，并补上 `workdir-unmount`，`audit-image` 改名为 `image-audit`；
  - CI 拆分为 `check.yml` 和 `build.yml`。
- **回退**：在 A/B 那个 change 落地之前，回退方式就是重刷上一次的镜像。

## Open Questions

- 根分区大小暂定 1024 MiB，A/B 落地时按 SD 卡容量重新规划。
- zsh 插件已经固定为 v0.7.1 和 0.8.0。以后升级时走普通的版本更新流程即可。
