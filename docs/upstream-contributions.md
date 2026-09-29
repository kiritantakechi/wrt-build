# Upstream contributions

Any PR, issue or push to a repository the maintainer does not own requires explicit consent first. The patches here are only prepared locally; whether and when to submit them is up to the maintainer.

| # | Repository | Patch | Status | Link |
|---|---|---|---|---|
| 1 | openwrt/openwrt | `docs/upstream/0001-build-make-the-EROFS-compression-selectable.patch` | Prepared, not submitted (awaiting approval) | — |
| 2 | openwrt/openwrt | `docs/upstream/0002-config-kernel-add-F2FS-compression-options.patch` | Prepared, not submitted (awaiting approval) | — |
| 3 | qemu/qemu | `patches/qemu/0001-hw-sd-sdhci-pci-migrate-the-PCI-device-state.patch` | Carried in `flake.nix`; not submitted (awaiting approval) | — |
| 4 | EHfive/einat-ebpf | `feed/net/einat/patches/100-mark-inbound-packets-translated-back.patch` | Carried in the einat package; not submitted (awaiting approval) | — |
| 5 | openwrt/openwrt | `patches/openwrt/0007-qosify-configure-the-daemon-whenever-it-comes-up.patch` | Carried in the patch series; not submitted (awaiting approval) | — |
| 6 | openwrt/openwrt | `patches/openwrt/0008-rockchip-set-a-NIC-s-IRQ-affinity-only-when-that-NIC.patch` | Carried in the patch series; not submitted (awaiting approval) | — |

## 1. EROFS compression algorithm

Problem: `include/image.mk:110` tests `CONFIG_EROFS_FS_ZIP_LZMA`, but that symbol does not exist; the Kconfig option is named `KERNEL_EROFS_FS_ZIP_LZMA`. So the LZMA branch never runs, and every EROFS image is in fact compressed with lz4hc.

Why a rename alone is not enough: `KERNEL_EROFS_FS_ZIP_LZMA` has no prompt and defaults to y when EROFS is enabled. With only the rename, every EROFS build would **silently switch to LZMA**, and this project's images would change with it, whereas we chose lz4hc.

What the patch does: it adds a `compression` choice that defaults to lz4hc, matching the current actual behavior; choosing LZMA also selects the kernel's LZMA support. `image.mk` now tests this choice instead.

## 2. Kernel options for F2FS compression

Problem: fstools can format the overlay as compressed f2fs via `fstools_overlay_compression_type=`, but `config/Config-kernel.in` has no matching `KERNEL_F2FS_*` options, so the build configuration cannot select them.

What the patch does: it adds `KERNEL_F2FS_FS_COMPRESSION` and each algorithm option beneath it (LZO, LZO-RLE, LZ4, LZ4HC, ZSTD). The kernel defaults all of these options to y, and if any of them has no value the build stops, so each one needs a matching `KERNEL_*`.

How this project handles it: it does not depend on this patch; instead, the upstream-native kernel config overlay (`config/kernel.config` → `env/kernel-config`) provides the same options. Once upstream accepts the patch, we can switch back to `CONFIG_KERNEL_F2FS_*` in the seed.

Verification log (1 and 2): 2026-09-28, both patches apply cleanly with `git am` onto openwrt `1019293`, as pinned by the lock.

## 3. sdhci-pci loses its card on loadvm (QEMU)

Problem: `sdhci-pci` takes the migration description of the sysbus SDHCI variants, `sdhci_vmstate`, which holds only the controller registers. Its PCI configuration space is never saved, so after `loadvm` (or a migration) the BAR is unmapped, every register reads as all ones, and the guest loses its card ("Controller never released inhibit bit(s)").

Why it matters here: since r4s-ab-rollback, the emulator boots the factory image from an SD card on `sdhci-pci`, and the tests return the machine to a `savevm` snapshot between every two tests.

What the patch does: it gives `sdhci-pci` a description of its own: the PCI device state first, then the shared controller state. `flake.nix` builds the emulator's QEMU (aarch64 guests only) with it, and with every other patch in `patches/qemu/`.

Verification log: 2026-09-29, QEMU 11.1.1 builds with the patch, and the emulation tests, which restore a snapshot between every two tests, pass with the SD card.

## 4. einat marks the inbound packets it translates back

Problem: einat reverse-translates inbound packets in its tc ingress program, before netfilter sees them, and leaves no trace of having done so. A firewall behind it cannot tell a packet einat let in (a reply, or a new flow to a mapped port under full-cone filtering) from one that arrived for an internal address by other means (a spoofed destination). The usual answer, accepting every forwarded packet from the external zone towards the internal ones, accepts both.

What the patch does: an `inbound_mark` option (`--inbound-mark` on the command line), ORed into `skb->mark` by `ingress_rev_snat` after a successful reverse translation. It is a read-only global of the BPF object, 0 by default, which marks nothing, so without the option einat behaves as before. Hairpinned packets never pass `ingress_rev_snat` (egress redirects them), so they stay unmarked. The Rust side adds the option to the configuration and the command line (hexadecimal accepted) and passes it with the other globals; the rodata struct gains explicit padding, as the loader requires a layout without implicit padding.

How this project uses it: einat runs with `--inbound-mark 0x20000000` (the bit `config/marks.tsv` gives it), and its init script adds one fw4 rule that accepts forwarded packets from wan to lan carrying the bit (r4s-ebpf-datapath design D2, D3).

Verification log: 2026-09-29, the patch applies to einat-ebpf 0.1.11 (`ba647ce`) and builds with the aya loader.

## 5. qosify stays unconfigured after a slow start

Problem: qosify's init script waits 10 seconds for the daemon's ubus object and, if it has not appeared by then, gives up on configuring it: no shaping and no classification until the next reload, with only "Command failed: Request timed out" in the log. The daemon registers once its BPF programs are loaded, which on a busy boot takes longer; the emulator hit it on every boot.

What the patch does: `service_running` waits up to two minutes, in the background, and configures the daemon when it appears, so the boot does not wait along. `PKG_RELEASE` goes to 2.

Verification log: 2026-09-29, in the emulator qosify now attaches cake and its classifiers to pppoe-wan at boot (`tests/network/test_qos.py`, `test_tc_hook_order.py`).

## 6. rockchip: IRQ affinity for every net device

Problem: `40-net-smp-affinity` runs its whole body on every net `add` event, whatever the device: each bridge, veth or tunnel sets every NIC's IRQ affinity again and waits up to ten seconds per NIC for the IRQ to show in `/proc/interrupts`. procd runs hotplug scripts one after another, so a NIC whose IRQ carries another name (the emulator's virtio NICs) holds up every later net event: dae's own veths and a container bridge were bound minutes late.

What the patch does: `set_interface_core` returns unless the event is for that interface. At boot each NIC's own event still sets its affinity, so the result on the device is the same.

Verification log: 2026-09-29, a bridge created after dae is bound within the spec's 60 seconds (`tests/network/test_transparent_proxy.py`).

