# Kernel configuration

Kernel configuration comes from three sources, each responsible for one kind of setting:

| Source | What goes there | Examples |
|---|---|---|
| `CONFIG_KERNEL_*` in `config/kernel.seed` | Symbols for which upstream provides an option in `Config-kernel.in` and that affect package dependencies or host tools | BTF, `BPF_EVENTS`, cgroup |
| `config/kernel.config` | Symbols with no upstream `CONFIG_KERNEL_*` option | F2FS compression, QEMU virt drivers |
| `patches/openwrt/` | Only BBRv3 modifies kernel source | `hack-6.18/960-bbr3-*` |

`scripts/config.sh` links `config/kernel.config` to `$TREE/env/kernel-config`. It is the last layer of `LINUX_KCONFIG_LIST` (`include/target.mk`), a mechanism upstream supports natively. After the build, `scripts/build.sh` checks it line by line: every line of the kernel config overlay must appear verbatim in the kernel's `.config`.

## Adding symbols to the kernel config overlay

Enabling a symbol often makes a batch of new symbols beneath it visible. Kernel configuration stops outright when it meets a visible symbol with no value, so the new symbols must be given values as well. To find them:

```sh
# inside wrt-build-fhs, after one complete build of the tree
K=$(ls -d "$WRT_WORKDIR"/openwrt/build_dir/target-*/linux-rockchip_armv8/linux-[0-9]*)
TC=$(ls -d "$WRT_WORKDIR"/openwrt/staging_dir/toolchain-aarch64_*)
cp "$K/.config" /tmp/try.config
printf '%s\n' CONFIG_NEW_SYMBOL=y >>/tmp/try.config
make -s -C "$K" ARCH=arm64 CROSS_COMPILE="$TC/bin/aarch64-openwrt-linux-musl-" \
  KCONFIG_CONFIG=/tmp/try.config listnewconfig
```

Every symbol listed must be given a value in the kernel config overlay. Also watch the dependencies: for example, `VIRTIO_PCI` sits under `VIRTIO_MENU`, so writing only `VIRTIO_PCI=y` gets silently dropped. The line-by-line check after the build exists to catch exactly this.

## Cost of the virt driver group

So that the shipped kernel can boot directly in the QEMU `virt` machine, the kernel config overlay builds in the generic PCIe host controller, virtio-pci, virtio-blk, virtio-net and the i6300esb watchdog. The PL011 serial console is already built in by the rockchip config. Only modern virtio is enabled, not legacy, and all other virtio devices are off.

Measured (2026-09-28, kernel 6.18.52): the added object files total 141,430 bytes (text + data + bss), about 138 KiB; the `Image` with BTF is 26,867,720 bytes. The R4S has none of these devices, so these drivers are never probed; they only take up this space.

| Object file | Bytes |
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
