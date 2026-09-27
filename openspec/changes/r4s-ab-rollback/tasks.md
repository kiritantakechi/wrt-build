# Tasks

## 1. 引导程序

- [ ] 1.1 在 `docs/dev-setup.md` 里补充串口调试的准备：USB-TTL 3.3V、1500000 波特率、接线方式。验证：接好串口后上电，能看到 U-Boot 输出，并能中断进入命令行。
- [ ] 1.2 写补丁，只对 `nanopi-r4s-rk3399` 这个变体追加 design D3 里的 U-Boot 配置：bootcount、可写变量列表、看门狗、启动命令、环境文件。验证：构建出的 U-Boot `.config` 里这些选项都在，其他 rockchip 变体的配置不受影响。
- [ ] 1.3 以补丁形式加入 `nanopi-r4s-wrt` 默认环境文件，定义 `wrt_boot`、`altbootcmd`、`wrt_fallback`，并把所有运行时变量登记为可写。验证：串口里 `printenv` 能看到这些逻辑；分别设置 `boot_slot` 为 a、b 和一个无效值时，`/proc/cmdline` 里的 `wrt.slot` 分别是 a、b、a。
- [ ] 1.4 验证启动逻辑不会被持久环境覆盖：在串口里对 `bootcmd` 执行 `setenv` 和 `saveenv` 后重启。验证：仍然执行内置的 `wrt_boot`。

## 2. 镜像

- [ ] 2.1 实现 `scripts/gen_image_ab.sh`，并在 rockchip 镜像配方里新增出厂镜像的生成规则（四个分区，环境区填零）。验证：对产出的镜像运行 `fdisk -l`，看到四个主分区，顺序和大小符合 design D1；总大小不超过 3.5 GiB。
- [ ] 2.2 新增单槽升级 tar 的生成规则（`kernel` 为 boot 分区的 ext4 镜像，`root` 为 EROFS），并附加元数据。验证：`tar tf` 只列出 kernel、root、CONTROL 三项；`fwtool` 能读出其中的板型元数据。
- [ ] 2.3 把出厂镜像写入一张 4 GB 的 SD 卡并启动。验证：首次从槽位 A 启动；执行 `wrt-slot switch`（见 3.2）后，能从槽位 B 启动。

## 3. Linux 侧环境读写与命令行工具

- [ ] 3.1 写补丁，在 uboot-envtools 的 rockchip 配置里加入 R4S（启动盘动态确定，偏移 `0x3F8000`，大小 `0x8000`）。验证：设备上 `fw_printenv boot_slot` 能读到值；`fw_setenv` 之后在串口的 `printenv` 里能看到变化。
- [ ] 3.2 在自有 feed 里实现 `wrt-slot`，提供 `status` 和 `switch` 两个子命令。验证：`status` 输出当前槽位、是否已确认、`bootcount` 和最近一次检查结果；`switch` 之后重启，进入另一个槽位并处于试运行状态。

## 4. 健康检查

- [ ] 4.1 在自有 feed 里实现 `wrt-healthcheck`：内置检查项、`/etc/healthcheck.d/` 的注册机制、单项和总时限、写出 JSON 结果文件。配套一组用模拟命令驱动的 shell 测试，并加入 CI。验证：测试覆盖通过、内置项失败、注册项失败、注册项超时、WAN 断开仍判定通过这五种情况，全部通过。
- [ ] 4.2 实现试运行和已确认两种状态下的处理：试运行通过就清零变量，失败就重启；已确认失败只记录。验证：4.1 的测试新增三个用例，分别对应规格里的三个场景，全部通过。

## 5. 升级流程

- [ ] 5.1 写补丁修改 `platform.sh`：检查镜像格式；只写非活动槽位；清零 overlay 起始区域；设置三个环境变量。验证：在槽位 A 上升级，升级前后 boot-A、root-A 和引导区域的 sha256 保持不变。
- [ ] 5.2 写补丁修改 `platform_copy_config` 和 `79_move_config`，让它们按槽位工作。验证：保留配置升级后，新槽位的配置与升级前一致；用 `-n` 升级后是出厂配置；新槽位里看不到旧 overlay 中的残留文件。
- [ ] 5.3 用其他设备的镜像，以及一个整盘镜像，分别执行升级。验证：两种情况都被拒绝，两个槽位的校验和都没有变化。

## 6. 回滚演练（真机，结果记录在 `docs/validation/ab-rollback.md`）

- [ ] 6.1 正常升级：从 A 升级到 B。验证：进入 B 后处于试运行状态；300 秒内被确认；`bootcount` 和 `upgrade_available` 都是 0。
- [ ] 6.2 坏内核：升级一个内核损坏的镜像。验证：先在同一次上电中尝试另一个槽位，或者经过至多 4 次启动后，回到原槽位，并且 `upgrade_available` 为 0。
- [ ] 6.3 panic：在试运行期间执行 `echo c > /proc/sysrq-trigger`。验证：10 秒内重启，`bootcount` 加一；反复触发后回滚到原槽位。
- [ ] 6.4 健康检查失败：临时注册一个必定失败的检查项，然后升级。验证：几次重启之后回滚到原槽位，失败的检查项名称出现在日志里。
- [ ] 6.5 写入时断电：在 `platform_do_upgrade` 执行 `dd` 期间拔掉电源。验证：重新上电后从原槽位正常启动。
- [ ] 6.6 WAN 断开：拔掉 WAN 网线后执行升级。验证：新槽位照样被确认，没有回滚。
- [ ] 6.7 手动退回：在已确认的 B 上执行 `wrt-slot switch`。验证：进入 A 并处于试运行状态，随后被确认。

## 7. 文档与迁移

- [ ] 7.1 编写 `docs/ab-layout.md`：分区偏移、环境变量的含义、状态流转、手动恢复方法（串口里怎么设置 `boot_slot`）。验证：按文档在串口里手动切换一次槽位，能成功。
- [ ] 7.2 编写 `docs/migration-single-to-ab.md`，内容对应 design 的 Migration Plan。验证：在一台跑着单槽系统的设备上按文档迁移，配置恢复后与迁移前一致。
