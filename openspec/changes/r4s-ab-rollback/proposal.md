# Proposal

## Why

上游 rockchip 的 sysupgrade 会直接覆盖正在运行的根分区（见 `target/linux/rockchip/armv8/base-files/lib/upgrade/platform.sh`）。新镜像起不来，或者写到一半断电，都只能把 SD 卡拔下来重刷。

本项目每周跟进上游 main，碰上“新构建开不了机”的概率比用稳定版高。R4S 又只能从 SD 卡启动，所以需要在不碰硬件的情况下自动恢复到上一个能用的系统。

## What Changes

- **BREAKING（相对上游布局）：分区布局变了**
  - SD 卡改为 MBR 四个主分区：boot-A、root-A、boot-B、root-B。
  - 每个 root 槽位里是一份 EROFS 加它自己的 f2fs overlay。
  - 首次安装必须刷出厂镜像；上游布局的设备不能原地升级过来。
- **产出两类镜像**
  - 出厂镜像：包含两个槽位。
  - 单槽升级镜像：带 metadata，可以被 sysupgrade 校验。
- **U-Boot 选槽**
  - 在 U-Boot 2026.07 上通过 `UBOOT_CUSTOMIZE_CONFIG` 打开 `BOOTCOUNT_LIMIT`。
  - 环境变量存放在 SD 卡分区前的空隙里。R4S 的 U-Boot 默认配置本来就把它放在 `0x3F8000`，大小 32 KiB，和上游 uboot-envtools 给 orangepi-r1-plus 的设置一样。
  - 选槽逻辑编进 U-Boot 的启动命令，不依赖两个槽共用的启动脚本。
  - bootcount 超过 `bootlimit` 后，由 `altbootcmd` 切换到另一个槽位。
- **硬件看门狗**
  - 启用 RK3399 的 dw_wdt，由 procd 定期喂狗。
  - 内核卡死会变成复位，并让 bootcount 加一。
  - 内核 panic 后自动重启。rockchip 的内核配置把 `PANIC_TIMEOUT` 设成了 0，不处理的话 panic 之后会一直卡住。
- **严格健康检查**
  - 判定启动成功的条件：系统进入用户态，br-lan 起来，dropbear 和 uhttpd 在监听，已注册的组件检查项全部通过（例如 dae、einat 的 BPF 程序已挂载）。
  - 不检查 WAN，避免运营商断网时误回滚。
  - 检查通过后用 `fw_setenv` 清零 bootcount，并把当前槽位确认为好的。
- **sysupgrade 流程**
  - 只写非活动槽位。
  - 配置备份放进目标槽位的 boot 分区，首次启动时由改成按槽位查找的 `79_move_config` 迁移过去。
  - 只有新槽位通过健康检查后，它才成为默认槽位。
- **uboot-envtools**：加上 R4S 的环境变量位置，让 Linux 这边可以读写。
- **在模拟器中验证整条 A/B 链路**
  - 同一版本的 U-Boot 源码再编一个 `qemu_arm64` 变体，用同一份选槽逻辑，只换板级常量（MMC 编号、串口、设备树来源）。
  - 模拟器用 `sdhci-pci` 挂载 SD 卡，出厂镜像原样作为 SD 卡，环境变量同样在 `0x3F8000`。
  - 选槽、计数、回滚、升级、断电、健康检查的规格场景都写成 `just test` 里的自动用例。
  - 只有 RK3399 从 SD 卡启动和 DesignWare 看门狗这两条链路留给真机冒烟。

## Capabilities

### New Capabilities

- `firmware/ab-layout`：A/B 分区布局，以及出厂镜像和单槽升级镜像两种格式。
- `firmware/boot-rollback`：U-Boot 选槽、bootcount、看门狗和自动回滚。
- `firmware/health-check`：启动成功的判定条件、检查项的注册方式，以及确认当前槽位。
- `firmware/ab-upgrade`：写非活动槽位的 sysupgrade 流程和配置迁移。

### Modified Capabilities

（无。）

## Impact

- **要修改的上游文件**：
  - rockchip 镜像配方（`target/linux/rockchip/image/Makefile`、`armv8.mk`）和启动脚本；
  - `package/boot/uboot-rockchip/Makefile`；
  - base-files 里的 `platform.sh` 和 `79_move_config`；
  - uboot-envtools 的 rockchip 配置。
- **新增的自有内容**：
  - `uboot/` 下的公共逻辑和两份板级常量；
  - 自有 feed 里的 `uboot-wrt-qemu`（只作为测试产物）、`wrt-slot`、`wrt-healthcheck`；
  - `config/kernel.config` 的 virt 驱动组里加一项 `MMC_SDHCI_PCI`；
  - `tests/firmware/` 下的四个用例模块，与四个规格一一对应。
- **依赖**：`r4s-build-foundation`，包括 EROFS 根文件系统、补丁流程、测试框架和模拟环境。健康检查里数据面的那几项由 `r4s-ebpf-datapath` 注册。
- **U-Boot 不在 A/B 范围内**：U-Boot 在两个槽位之间共用，单槽升级镜像不会改写它。U-Boot 的更新是独立的低频操作，仍然是单点风险。
- **真机工作量**：只剩一次冒烟，即刷出厂镜像后运行 `just test-device`，其中两项需要人工断电或者制造卡死。回滚演练本身在 CI 里完成。
