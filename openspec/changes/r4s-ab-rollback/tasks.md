# Tasks

## 1. 引导程序（公共逻辑 + 两个板级构建）

- [ ] 1.1 编写 `uboot/wrt-ab.env`（公共逻辑），以及结构对称的 `uboot/board-r4s.env` 和 `uboot/board-qemu.env`（只含 design D3 列出的常量），并把所有运行时变量登记为可写。验证：规范检查确认两份板级文件包含的变量名完全相同，而且只有这些变量。
- [ ] 1.2 修改 `package/boot/uboot-rockchip/Makefile`，只对 `nanopi-r4s-rk3399` 变体生效：拼接环境文件，追加公共配置和 r4s 专有配置。验证：构建出的 U-Boot `.config` 里有这些选项；其他 rockchip 变体的 `.config` 与修改前相同。
- [ ] 1.3 在自有 feed 新增 `uboot-wrt-qemu` 包：从同一个 U-Boot 源码包构建 `qemu_arm64`，拼接 qemu 板级常量和公共逻辑，追加公共配置和 qemu 专有配置，产物只进测试目录。验证：规范检查确认它的 `PKG_VERSION` 和 `PKG_HASH` 与 `uboot-rockchip` 相同；在 QEMU 里 `printenv` 能看到 `wrt_boot`。
- [ ] 1.4 在 `config/kernel.config` 的 virt 驱动组里加入 `CONFIG_MMC_SDHCI_PCI=y`，并用 `listnewconfig` 补全子选项。验证：构建后的内核配置校验通过。

## 2. 镜像

- [ ] 2.1 实现 `scripts/gen_image_ab.sh`，并在 rockchip 镜像配方里新增出厂镜像的生成规则（四个分区，环境区填零）。验证：由 `tests/firmware/test_ab_layout.py` 核对分区表的顺序和大小，并确认总大小在 4 GB 以内。
- [ ] 2.2 新增单槽升级 tar 的生成规则，并附加元数据。验证：`test_ab_layout.py` 核对 tar 里只有 kernel、root、CONTROL 三项，而且元数据的板型正确。

## 3. Linux 侧

- [ ] 3.1 修改 uboot-envtools，加入 R4S 的配置。验证：在模拟器中，`fw_printenv boot_slot` 能读到值；`fw_setenv` 之后，重启进入 U-Boot 时 `printenv` 能看到变化。
- [ ] 3.2 在自有 feed 实现 `wrt-slot` 的 `status` 和 `switch` 两个子命令。验证：由 `test_boot_rollback.py` 里手动切换槽位的用例覆盖。
- [ ] 3.3 实现 `wrt-healthcheck`：内置检查项、`/etc/healthcheck.d/` 注册机制、单项和总时限、JSON 结果，以及试运行和已确认两种状态的处理。验证：由 `test_health_check.py` 覆盖 health-check 规格的全部场景。
- [ ] 3.4 修改 `platform.sh` 中的 `platform_check_image`、`platform_do_upgrade`、`platform_copy_config`，以及 `79_move_config`。验证：由 `test_ab_upgrade.py` 覆盖 ab-upgrade 规格的全部场景。

## 4. 模拟器用例（全部在 `just test` 中运行）

- [ ] 4.1 扩展模拟环境，支持 A/B 模式：用 `-bios` 加载 `uboot-wrt-qemu`，出厂镜像通过 `sdhci-pci` 作为 SD 卡挂载，磁盘写入可以限速（用于测试断电）。验证：模拟器自检用例覆盖 A/B 模式下的启动、断电和重启。
- [ ] 4.2 编写 `tests/firmware/test_ab_layout.py`，覆盖 ab-layout 规格的全部场景（4 GB 的场景用镜像大小来判断）。验证：用例全部通过。
- [ ] 4.3 编写 `tests/firmware/test_boot_rollback.py`，覆盖以下场景：按 a、b 和无效值选槽；持久环境覆盖不了启动逻辑；试运行三次失败后回滚；正常运行时不计数；加载失败时在同一次上电内切换槽位；两个槽位都失败时停在提示符；内核 panic 后 10 秒内重启并计数。验证：用例全部通过。
- [ ] 4.4 编写 `tests/firmware/test_health_check.py`：WAN 断开仍然通过、uhttpd 不监听时失败、注册的检查项失败或超时、试运行和已确认两种状态的处理、状态查询。验证：用例全部通过。
- [ ] 4.5 编写 `tests/firmware/test_ab_upgrade.py`：只写非活动槽位（校验和不变）、写到一半断电、新的 overlay、保留配置和不保留配置、进入试运行、拒绝不匹配的镜像、手动切换槽位。验证：用例全部通过；`spec-coverage` 显示这个 change 除了仅真机的场景外，没有未覆盖的场景。

## 5. 真机冒烟

- [ ] 5.1 编写 `@target("device")` 用例：U-Boot 从 SD 卡启动，并按 `boot_slot` 进入指定槽位；早期卡死时看门狗复位；用户态没有接管时复位。需要断电或者模拟卡死时，用例会提示人工操作。验证：在模拟器上运行时，这些用例被跳过并显示原因。
- [ ] 5.2 把出厂镜像刷进 SD 卡，运行 `just test-device <host>`。验证：报告全部通过，结果存档到 `docs/validation/ab-rollback-device.md`。

## 6. 文档与迁移

- [ ] 6.1 编写 `docs/ab-layout.md`：分区偏移、变量含义、状态流转、用串口手动恢复的方法。验证：按文档在模拟器的 U-Boot 提示符下手动切换一次槽位，能成功。
- [ ] 6.2 编写 `docs/migration-single-to-ab.md`，内容对应 design 的 Migration Plan。验证：在模拟器里按文档从单槽镜像迁移到 A/B 出厂镜像并恢复备份，配置与迁移前一致。
