# Design

## Context

动机见 proposal.md。以下现状都在上游源码里核对过（OpenWrt main `1019293`，U-Boot v2026.07）：

- **镜像生成**：`scripts/gen_image_generic.sh` 只支持“kernel + rootfs”两个分区；不带 GUID 时，boot 分区用 `make_ext4fs` 生成 ext4。
- **升级流程**：rockchip 的 `platform.sh` 直接把整个磁盘镜像 `dd` 到启动盘上；`79_move_config` 固定从第 1 个分区取 `sysupgrade.tgz`。
- **U-Boot 环境变量**：`configs/nanopi-r4s-rk3399_defconfig` 已经开了 `ENV_IS_IN_MMC`，`ENV_OFFSET=0x3F8000`；rockchip 加 MMC 时 `ENV_SIZE` 默认是 `0x8000`。
- **U-Boot 能力**：支持 `ENV_WRITEABLE_LIST`；`BOOTCOUNT_ENV` 只在 `upgrade_available` 为 1 时才计数并保存；R4S 的 defconfig 没开 `WDT`，但 `DESIGNWARE_WATCHDOG` 对 RK3399 默认为 y。
- **内核看门狗**：
  - `DW_WATCHDOG=y`；
  - `WATCHDOG_HANDLE_BOOT_ENABLED=y`：看门狗已经在运行时，由内核代为喂狗，直到用户态接管；
  - `WATCHDOG_OPEN_TIMEOUT=0`：内核会无限期地代为喂狗。
- **内核 panic**：rockchip 的 `PANIC_TIMEOUT=0`，panic 之后会一直卡住。
- **fstools**：overlay 放在 EROFS 结束处按 64 KiB 对齐后的位置。
- **foundation 提供的前提**：模拟环境（testing/emulation），它以 R4S 的板型身份运行出货镜像；以及 `config/kernel.config` 叠加机制。

## Goals / Non-Goals

**Goals:**
- 升级不碰当前在运行的槽位；新系统起不来时，不接触硬件就能自动恢复。
- 选槽逻辑固化在引导程序里，Linux 这边只读写三个变量。
- 健康检查可以扩展，后续 change 能往里注册检查项。
- 这套 A/B 状态机在模拟器里能跑通完整链路：U-Boot 同版本、同逻辑，SD 卡、分区、环境变量偏移都相同。

**Non-Goals:**
- U-Boot 本身的 A/B 和在线更新。U-Boot 只在刷出厂镜像时更新。
- 验证启动（签名 FIT、dm-verity）。探索阶段已经否决：R4S 的 SD 卡可以拔插，eFuse 也没烧。
- 数据面的检查项，它们由 `r4s-ebpf-datapath` 注册。

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

- **用 MBR**：与上游一致，四个主分区刚好够用。GPT 带不来额外好处，还会偏离上游。
- **boot 分区给 64 MiB**：打开 BTF、加上 virt 平台驱动之后，内核 FIT 会变大，这里留出余量。

### D2. 镜像产物

- **生成脚本**：`scripts/gen_image_ab.sh` 用 `ptgen` 生成四个分区，boot 分区沿用 `make_ext4fs`。
- **出厂镜像**：两个槽位内容相同，U-Boot 环境区全部填零，首次启动就进入槽位 A。
- **升级镜像**：`sysupgrade.tar`，复用 `Build/sysupgrade-tar`，里面是 `kernel`（boot 分区的 ext4 镜像）、`root`（EROFS）和 `CONTROL`，并用 `append-metadata` 附上元数据。
- **备选方案**：沿用整盘镜像再按分区截取。否决，因为整盘镜像带着 U-Boot 和分区表。

### D3. U-Boot：逻辑固化在二进制里，拆成“公共逻辑 + 板级常量”两层

```
uboot/wrt-ab.env          common state machine (single source of truth)
uboot/board-r4s.env       wrt_mmc=1  wrt_console=ttyS2,1500000
                          wrt_earlycon=uart8250,mmio32,0xff1a0000  wrt_fdt=      (FIT dtb)
uboot/board-qemu.env      wrt_mmc=0  wrt_console=ttyAMA0
                          wrt_earlycon=                            wrt_fdt=${fdtcontroladdr}
```

- **两份对称的构建**：每个 U-Boot 构建把“板级常量 + 公共逻辑”拼成 `ENV_SOURCE_FILE` 需要的文本环境文件。
  - 出货的 `nanopi-r4s-rk3399` 变体：修改 `package/boot/uboot-rockchip/Makefile`，通过 `UBOOT_CUSTOMIZE_CONFIG` 只对这个变体生效。
  - 测试用的 `qemu_arm64`：放在自有 feed 的 `uboot-wrt-qemu` 包里。它只作为测试产物，不进固件。
  - 两者的版本必须与 `uboot-rockchip` 完全一致，由规范检查保证。
- **两份构建共用的配置**：

```
--enable BOOTCOUNT_LIMIT --enable BOOTCOUNT_ENV --set-val BOOTCOUNT_BOOTLIMIT 3
--enable ENV_WRITEABLE_LIST
--set-str ENV_FLAGS_LIST_STATIC "boot_slot:sw,bootcount:dw,upgrade_available:dw,<runtime vars>:sw"
--enable USE_BOOTCOMMAND --set-str BOOTCOMMAND "run wrt_boot"
r4s only:  --enable WDT --enable WATCHDOG_AUTOSTART --set-val WATCHDOG_TIMEOUT_MSECS 60000
qemu only: --disable ENV_IS_IN_FLASH --enable ENV_IS_IN_MMC --set-val SYS_MMC_ENV_DEV 0
           --set-hex ENV_OFFSET 0x3F8000 --set-hex ENV_SIZE 0x8000
           --enable MMC --enable DM_MMC --enable MMC_SDHCI --enable MMC_PCI   (sdhci over PCI)
```

- **公共逻辑**：

```
wrt_boot:
  if boot_slot != b: boot_slot=a, bp=1, rp=2   else: bp=3, rp=4
  part uuid mmc ${wrt_mmc}:${rp} rootuuid
  load mmc ${wrt_mmc}:${bp} ${kernel_addr_r} kernel.img || run wrt_fallback
  bootargs = console=${wrt_console} [earlycon=${wrt_earlycon}] root=PARTUUID=${rootuuid}
             rw rootwait panic=5 watchdog.open_timeout=90 wrt.slot=${boot_slot}
             fstools_overlay_compression_type=zstd
  bootm ${kernel_addr_r} [- ${wrt_fdt}]

altbootcmd  (bootcount > bootlimit):
  boot_slot = other; upgrade_available=0; bootcount=0; saveenv; run wrt_boot

wrt_fallback (load failure, same power cycle):
  if wrt_tried unset: wrt_tried=1; boot_slot = other; run wrt_boot
  else: stop at U-Boot prompt (no loop)
```

- **只放开三个变量**：`ENV_WRITEABLE_LIST` 保证只有登记为可写的变量会从持久环境读入，所以逻辑永远来自二进制本身。启动时用 `setenv` 设置的每个临时变量也都必须登记为可写，这一点由模拟测试逐条覆盖，不必再等上机时接串口核对。
- **panic 相关的两个参数**：`panic=5` 覆盖 rockchip 的 `PANIC_TIMEOUT=0`；`watchdog.open_timeout=90` 限制内核代为喂狗的时间。
- **备选方案**：
  - 共用一个 boot.scr 来选槽。否决，因为它本身就是单点故障，而且会被持久环境覆盖。
  - 不用 `ENV_WRITEABLE_LIST`。否决，因为保存下来的旧逻辑会挡住以后的新逻辑。

### D4. Linux 侧读写环境变量

- **uboot-envtools**：打补丁加上 R4S 的配置，启动盘由 `export_bootdevice` 动态确定，偏移 `0x3F8000`，大小 `0x8000`。模拟器里用的是同一份配置，因为 SD 卡在那里同样是 MMC 设备。
- **`wrt-slot` 命令**：
  - `wrt-slot status` 输出当前槽位、`upgrade_available`、`bootcount`，以及最近一次健康检查的结果。
  - `wrt-slot switch` 用 `fw_setenv -s` 写入三个变量，然后重启。
- **对称设计**：`status` 和 `switch` 分别对应“读”和“写”，没有其他子命令。

### D5. 健康检查

`wrt-healthcheck` 在 `START=99` 启动：

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

- **为什么不检查 WAN**：运营商断网不代表系统坏了。
- **为什么已确认的系统失败时不重启**：已确认的系统没有回滚目标，重启只会原地打转。

### D6. 升级流程

- **`platform_check_image`**：只接受单槽升级 tar，并检查元数据。
- **`platform_do_upgrade`**：
  1. 由 `wrt.slot` 算出目标槽位；
  2. 把 kernel 和 root 分别 `dd` 到目标槽位的两个分区；
  3. 从 EROFS 结束位置按 64 KiB 对齐，把之后的 1 MiB 清零；
  4. 执行 `fw_setenv -s` 写入三个变量。
- **配置迁移**：`platform_copy_config` 把配置备份写到目标槽位的 boot 分区；`79_move_config` 按 `wrt.slot` 找到当前槽位的 boot 分区。

### D7. 验证方式：模拟器里的 A/B 链路

```
qemu-system-aarch64 -machine virt,gic-version=3 -cpu cortex-a72 -m 4G
  -bios u-boot.bin                         # uboot-wrt-qemu: same version + same wrt-ab.env
  -dtb r4s.dtb                             # R4S identity (foundation D14), also U-Boot's control DT
  -device sdhci-pci -device sd-card,drive=sd0 -drive if=none,id=sd0,file=factory-overlay.qcow2
  -netdev tap ... (foundation topology)  -device i6300esb -action watchdog=reset
```

- **在模拟器里测什么**：U-Boot 和 Linux 看到的都是 MMC 设备，出厂镜像原样作为 SD 卡，环境变量也在 `0x3F8000`。选槽、计数、回滚、同一次上电内切换槽位、两个槽位都失败时停在提示符、持久环境覆盖不了启动逻辑，这些 boot-rollback 的场景都走同一份 `wrt-ab.env`。
- **ab-upgrade、health-check、ab-layout**：它们的全部场景都在模拟器里用 Linux 侧的出货代码执行。
  - 写到一半断电：对磁盘写入限速，然后在 `dd` 期间结束 QEMU 进程。
  - 坏内核：在升级 tar 里放一个损坏的 FIT。
  - WAN 断开：`isp` 命名空间里不启动 PPPoE 服务端。
- **内核补充**：模拟用的 SD 卡控制器需要 `CONFIG_MMC_SDHCI_PCI=y`，由本 change 加进 `config/kernel.config` 的 virt 驱动组里。
- **只能留给真机的**（写成 `@target("device")` 用例）：
  1. RK3399 的 BootROM、TPL/SPL 从 SD 卡加载这版 U-Boot，并按 `boot_slot` 启动；
  2. DesignWare 看门狗在内核启动前就开始计时，内核早期卡死时会复位；
  3. 用户态在 `open_timeout` 内没有接管时会复位。

  其中第 2、3 项需要断电或者模拟卡死，由用例提示人工操作。

## Risks / Trade-offs

- **[`ENV_WRITEABLE_LIST` 漏登记了运行时变量]** 模拟测试会覆盖每一条启动路径，漏登记的变量在 CI 里就会暴露出来。
- **[模拟用的 U-Boot 与出货的 U-Boot 不一致]** 公共逻辑只有一份；规范检查会比对两个包的 U-Boot 版本；板级常量只允许包含 D3 列出的那些变量。
- **[U-Boot 只有一份]** 只有刷出厂镜像时才更新；U-Boot 的版本变化不会随每周 bump 下发到设备上。
- **[健康检查太严格导致误回滚]** 总时限 300 秒，单项时限 30 秒，只检查 LAN 侧和本机状态。
- **[overlay 残留被 fstools 误认]** 升级时清零 EROFS 之后的 1 MiB。
- **[真机上的 SD 卡编号]** 按 RK3399 惯例写成 1；真机冒烟用例第 1 项会确认。

## Migration Plan

1. 在单槽系统上执行 `sysupgrade -b`，导出配置备份。
2. 在电脑上把 A/B 出厂镜像写入 SD 卡（这是 BREAKING 变更）。
3. 启动后恢复第 1 步的备份。
4. 之后的升级都用单槽升级镜像。回退方式是 `wrt-slot switch`，或者等自动回滚生效。

## Open Questions

- 两个 root 分区都用 1024 MiB。SD 卡换大时可以调大，不影响规格。
