# 内核配置

内核配置有三个来源，各管一类：

| 来源 | 放什么 | 例子 |
|---|---|---|
| `config/kernel.seed` 里的 `CONFIG_KERNEL_*` | 上游在 `Config-kernel.in` 里提供了选项、而且会影响软件包依赖或宿主工具的符号 | BTF、`BPF_EVENTS`、cgroup |
| `config/kernel.config` | 上游没有提供 `CONFIG_KERNEL_*` 选项的符号 | F2FS 压缩、QEMU virt 驱动 |
| `patches/openwrt/` | 只有 BBRv3 修改内核源码 | `hack-6.18/960-bbr3-*` |

`config/kernel.config` 由 `scripts/config.sh` 链接到 `$TREE/env/kernel-config`。它是 `LINUX_KCONFIG_LIST` 的最后一层（`include/target.mk`），也是上游原生支持的机制。构建完成后，`scripts/build.sh` 会逐行核对：叠加文件里的每一行都必须原样出现在内核的 `.config` 中。

## 往叠加文件里加符号

打开一个符号，常常会让它下面的一批新符号变得可见。内核配置遇到没有取值的可见符号时会直接停下，所以新符号必须一起写明取值。找出它们的办法：

```sh
# inside wrt-build-fhs, after one complete build of the tree
K=$(ls -d "$WRT_WORKDIR"/openwrt/build_dir/target-*/linux-rockchip_armv8/linux-[0-9]*)
TC=$(ls -d "$WRT_WORKDIR"/openwrt/staging_dir/toolchain-aarch64_*)
cp "$K/.config" /tmp/try.config
printf '%s\n' CONFIG_NEW_SYMBOL=y >>/tmp/try.config
make -s -C "$K" ARCH=arm64 CROSS_COMPILE="$TC/bin/aarch64-openwrt-linux-musl-" \
  KCONFIG_CONFIG=/tmp/try.config listnewconfig
```

列出来的每一个符号都要在叠加文件里给出取值。还要注意依赖：比如 `VIRTIO_PCI` 挂在 `VIRTIO_MENU` 下面，只写 `VIRTIO_PCI=y` 会被静默丢掉。构建后的逐行核对就是为了拦住这种情况。

## virt 驱动组的代价

为了让出货内核能直接在 QEMU `virt` 机器里启动，叠加文件内置了通用 PCIe 主机控制器、virtio-pci、virtio-blk、virtio-net 和 i6300esb 看门狗。PL011 串口在 rockchip 的配置里本来就是内置的。只启用现代 virtio，不启用 legacy，其他 virtio 设备一律关闭。

实测（2026-09-28，内核 6.18.52）：新增的目标文件合计 141,430 字节（text + data + bss），约 138 KiB；带 BTF 的 `Image` 为 26,867,720 字节。R4S 上没有这些设备，这些驱动不会被探测到，只占用这部分空间。

| 目标文件 | 字节 |
|---|---|
| `drivers/net/virtio_net.o` | 57,861 |
| `drivers/virtio/virtio_ring.o` | 23,332 |
| `drivers/block/virtio_blk.o` | 11,463 |
| `drivers/net/net_failover.o` | 7,019 |
| `drivers/virtio/virtio_pci_modern.o` | 6,788 |
| `drivers/virtio/virtio.o` | 5,908 |
| `drivers/virtio/virtio_pci_common.o` | 5,572 |
| `drivers/virtio/virtio_pci_modern_dev.o` | 4,944 |
| `net/core/failover.o` | 2,819 |
| `drivers/watchdog/i6300esb.o` | 2,366 |
| `drivers/pci/controller/pci-host-generic.o` | 1,783 |
| `drivers/virtio/virtio_anchor.o` | 112 |
