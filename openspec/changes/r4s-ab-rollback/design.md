# Design

## Context

动机见 proposal.md。以下现状都在上游源码里核对过（OpenWrt main `1019293`，U-Boot v2026.07）：

- **镜像生成**：`scripts/gen_image_generic.sh` 只支持“kernel + rootfs”两个分区。不带 GUID 时，boot 分区用 `make_ext4fs` 生成 ext4。
- **升级流程**：rockchip 的 `platform.sh` 直接把整个磁盘镜像 `dd` 到启动盘上。`79_move_config` 固定从第 1 个分区取 `sysupgrade.tgz`。
- **U-Boot 环境变量**：`configs/nanopi-r4s-rk3399_defconfig` 已经开了 `ENV_IS_IN_MMC`，`ENV_OFFSET=0x3F8000`；rockchip 加 MMC 时 `ENV_SIZE` 默认是 `0x8000`（`env/Kconfig:682`）。
- **U-Boot 看门狗**：R4S 的 defconfig 没开 `WDT`。`DESIGNWARE_WATCHDOG` 对 RK3399 默认为 y（`drivers/watchdog/Kconfig:74-77`）。
- **U-Boot 其他能力**：支持 `ENV_WRITEABLE_LIST`（`env/Kconfig:852`）；`BOOTCOUNT_ENV` 只在 `upgrade_available` 为 1 时才计数并保存（`drivers/bootcount/Kconfig:63`）。
- **内核看门狗**：
  - `DW_WATCHDOG=y`（`armv8/config-6.18:244`）。
  - `WATCHDOG_HANDLE_BOOT_ENABLED=y`：看门狗已经在运行时，由内核代为喂狗，直到用户态接管。
  - `WATCHDOG_OPEN_TIMEOUT=0`：内核会无限期地代为喂狗。
- **内核 panic**：rockchip 的 `PANIC_TIMEOUT=0`（`armv8/config-6.18:482`），panic 之后会一直卡住。
- **fstools**：overlay 放在 EROFS 结束处按 `ROOTDEV_OVERLAY_ALIGN`（64 KiB）对齐后的位置（`libfstools/rootdisk.c`）。

## Goals / Non-Goals

**Goals:**
- 升级不碰当前在运行的槽位；新系统起不来时，不接触硬件就能自动恢复。
- 选槽逻辑固化在引导程序里，Linux 这边只读写三个变量。
- 健康检查可以扩展，后续 change 能往里注册检查项。

**Non-Goals:**
- U-Boot 本身的 A/B 和在线更新。U-Boot 只在刷出厂镜像时更新。
- 验证启动（签名 FIT、dm-verity）。已经在探索阶段评估过并否决：R4S 的 SD 卡可以拔插，eFuse 也没烧。
- 数据面的检查项。它们由 `r4s-ebpf-datapath` 注册。

## Decisions

### D1. 分区布局

```
offset        content                         size
0x8000        idbloader (TPL + SPL)           < 4 MiB
0x3F8000      U-Boot env                      32 KiB
0x800000      u-boot.itb (U-Boot + TF-A)      < 24 MiB
32 MiB        p1 boot-A   ext4                64 MiB   kernel.img (FIT), sysupgrade.tgz handoff
              p2 root-A                       1024 MiB [EROFS][64K align][f2fs overlay]
              p3 boot-B   ext4                64 MiB
              p4 root-B                       1024 MiB
total ~ 2.2 GiB  -> fits a 4 GB card
```

- **为什么用 MBR**：上游 rockchip 就用 MBR，四个主分区刚好够用，也不用改 U-Boot 和 Linux 的分区识别方式。
- **为什么 boot 分区给 64 MiB**：上游默认是 16 MiB，但打开 BTF 之后内核 FIT 会变大，这里留出余量。
- **备选方案**：GPT。否决，因为它带不来额外好处，还会偏离上游。

### D2. 镜像产物

- **新增生成脚本**：写一个 `scripts/gen_image_ab.sh`，用 `ptgen` 连续给出四个 `-p` 参数生成分区表。boot 分区的做法沿用 `make_ext4fs`。
- **出厂镜像** `factory.img.gz`：两个槽位的内容相同，U-Boot 环境区全部填零，这样首次启动用默认值，也就进入槽位 A。
- **升级镜像** `sysupgrade.tar`：
  - 复用上游现成的 `Build/sysupgrade-tar`，里面是 `sysupgrade-<board>/{kernel,root,CONTROL}`。其中 `kernel` 是 boot 分区的 ext4 镜像，`root` 是 EROFS 镜像。
  - 用 `append-metadata` 附上元数据，供 `fwtool` 校验。
- **备选方案**：沿用整盘镜像再按分区截取。否决，因为整盘镜像里带着 U-Boot 和分区表，违反 ab-layout 规格。

### D3. U-Boot：选槽逻辑编进二进制，只放开三个变量

补丁修改 `package/boot/uboot-rockchip/Makefile`，只针对 `nanopi-r4s-rk3399` 这个变体追加配置：

```
--enable BOOTCOUNT_LIMIT --enable BOOTCOUNT_ENV --set-val BOOTCOUNT_BOOTLIMIT 3
--enable ENV_WRITEABLE_LIST
--set-str ENV_FLAGS_LIST_STATIC "boot_slot:sw,bootcount:dw,upgrade_available:dw,<runtime vars>:sw"
--enable WDT --enable WATCHDOG_AUTOSTART --set-val WATCHDOG_TIMEOUT_MSECS 60000
--enable USE_BOOTCOMMAND --set-str BOOTCOMMAND "run wrt_boot"
--set-str ENV_SOURCE_FILE "nanopi-r4s-wrt"
```

默认环境由一个文本格式的环境文件提供，作为补丁放进 `package/boot/uboot-rockchip/patches/`。逻辑如下：

```
wrt_boot:
  if boot_slot != b: boot_slot=a, bp=1, rp=2   else: bp=3, rp=4
  rootuuid = part uuid mmc <sd>:<rp>
  load mmc <sd>:<bp> kernel.img  || run wrt_fallback
  bootargs = console=ttyS2,1500000 earlycon=... root=PARTUUID=<rootuuid> rw rootwait
             panic=5 watchdog.open_timeout=90 wrt.slot=<boot_slot>
             fstools_overlay_compression_type=zstd
  bootm

altbootcmd  (bootcount > bootlimit):
  boot_slot = other; upgrade_available=0; bootcount=0; saveenv; run wrt_boot

wrt_fallback (load failure, same power cycle):
  if wrt_tried unset: wrt_tried=1; boot_slot = other; run wrt_boot
  else: stop at U-Boot prompt (no loop)
```

- **只放开三个变量的原因**：
  - `ENV_WRITEABLE_LIST` 保证只有列出来的变量会从持久环境读入。`wrt_boot`、`altbootcmd`、`bootcmd` 这些逻辑永远来自二进制本身，满足“启动逻辑不能被持久环境覆盖”这条规格。
  - 代价是：启动逻辑在运行时用 `setenv` 设置的每个临时变量（`bootargs`、`rootuuid`、`bp`、`rp`、`wrt_tried` 等），都必须登记为可写，否则设置会失败。任务 1.3 会逐一核对。
- **两处 panic 相关的参数**：
  - `panic=5` 覆盖了 rockchip 的 `PANIC_TIMEOUT=0`。
  - `watchdog.open_timeout=90` 限制内核代为喂狗的时间：用户态 90 秒内不接管，设备就复位。
- **SD 卡的编号**：U-Boot 里 SD 卡的 mmc 编号要上机确认。在 RK3399 上，sdmmc 通常是 mmc 1。这是一个延后确认项，不影响设计。
- **备选方案**：
  - 沿用 boot.scr，在脚本里选槽。否决，因为两个槽共用这个脚本，它本身就是单点故障，而且会被持久环境覆盖。
  - 不用 `ENV_WRITEABLE_LIST`。否决，因为 `BOOTCOUNT_ENV` 的 `saveenv` 会把整份环境写进 SD 卡，以后 U-Boot 的启动逻辑改了，会被存下来的旧逻辑挡住。

### D4. Linux 侧读写环境变量

- **envtools 配置**：打一个补丁，在 uboot-envtools 的 rockchip 配置里加上 R4S，参数是启动盘、`0x3F8000`、`0x8000`。启动盘由 `export_bootdevice` 动态确定，避免把 mmcblk 的编号写死。这个补丁可以提交给上游。
- **命令行工具**：自有 feed 新增 `wrt-slot`，提供两个子命令：
  - `wrt-slot status`：输出当前槽位（取自 `/proc/cmdline` 里的 `wrt.slot`）、`upgrade_available`、`bootcount`，以及最近一次健康检查的结果。
  - `wrt-slot switch`：用 `fw_setenv -s` 一次性写入 `boot_slot=<另一个槽位>`、`upgrade_available=1`、`bootcount=0`，然后重启。

### D5. 健康检查

自有 feed 新增 `wrt-healthcheck` 包，由 procd 在 `START=99` 启动：

```
wait up to 300s, poll every 10s:
  builtin: ubus system ready; network.interface.lan up with IPv4;
           dropbear listening on LAN addr :22; uhttpd listening on LAN addr :80
  registered: /etc/healthcheck.d/*  (executable, exit 0 = pass, 30s timeout each)
result -> /var/run/wrt-healthcheck.json (time, pass/fail, failed items)
trial (upgrade_available=1): pass -> fw_setenv -s {bootcount 0, upgrade_available 0}
                             fail/timeout -> logger + reboot
confirmed: fail -> logger only
```

- **为什么不检查 WAN**：运营商断网不代表系统坏了，把 WAN 算进去会导致误回滚。
- **为什么已确认的系统失败时不重启**：这时 `upgrade_available` 为 0，没有回滚目标，重启只会原地打转。

### D6. 升级流程

对 `platform.sh` 的补丁：

- **`platform_check_image`**：只接受单槽升级 tar，检查里面的成员和元数据；整盘镜像或其他格式一律拒绝。
- **`platform_do_upgrade`**：
  1. 从 `wrt.slot` 算出目标槽位；
  2. 把 `kernel` 成员 `dd` 到目标 boot 分区，把 `root` 成员 `dd` 到目标 root 分区；
  3. 从 EROFS 结束位置按 64 KiB 向上对齐，把之后的 1 MiB 清零，让 fstools 在首次启动时重新格式化 overlay；
  4. 执行 `fw_setenv -s`：`boot_slot=<目标>`、`upgrade_available=1`、`bootcount=0`。
- **`platform_copy_config`**：挂载目标槽位的 boot 分区，写入 `sysupgrade.tgz`。
- **`79_move_config`**：改为根据 `wrt.slot` 找到当前槽位的 boot 分区（a 对应 p1，b 对应 p3）。

因为整个过程都不碰活动槽位，写到一半断电也只影响非活动槽位。

## Risks / Trade-offs

- **[`ENV_WRITEABLE_LIST` 漏登记了运行时变量，导致启动失败]** → 上机时接串口逐条核对；首次验证必须在有串口的条件下进行。
- **[没有串口就无法调试引导阶段]** → 硬件前提是一根 USB-TTL 串口线（3.3V，1500000 波特率），写进 `docs/dev-setup.md`。
- **[U-Boot 只有一份]** 只有刷出厂镜像时才更新 U-Boot。上游 U-Boot 的版本变化不会随每周 bump 下发到设备上。
- **[SD 卡在 U-Boot 和 Linux 里编号不同]** → U-Boot 的编号上机确认；Linux 这边一律用 `export_bootdevice` 动态确定。
- **[健康检查太严格导致误回滚]** → 总时限设为 300 秒，单项时限 30 秒；检查项只看 LAN 侧和本机状态。
- **[overlay 区域有残留，被 fstools 误认成有效 overlay]** → 升级时清零 EROFS 之后的 1 MiB。
- **[试运行期间每次启动都写一次 SD 卡]** 只在试运行期间发生，次数不超过 4 次，可以接受。

## Migration Plan

1. 在单槽系统上执行 `sysupgrade -b`，导出配置备份。
2. 在电脑上把 A/B 出厂镜像写入 SD 卡（这是 BREAKING 变更，无法原地升级）。
3. 启动后在 LuCI 里恢复第 1 步的备份。
4. 之后的升级都用单槽升级镜像。回退方式是 `wrt-slot switch`，或者等自动回滚生效。

## Open Questions

- U-Boot 里 SD 卡的 mmc 编号（预期是 1）要上机确认。这只影响默认环境里的一个常量。
- 两个 root 分区都用 1024 MiB。如果以后 SD 卡换得更大，可以调大，不影响规格。
