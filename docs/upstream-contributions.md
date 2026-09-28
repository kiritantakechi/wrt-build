# Upstream contributions

Any PR, issue or push to a repository the maintainer does not own requires explicit consent first. The patches here are only prepared locally; whether and when to submit them is up to the maintainer.

| # | Repository | Patch | Status | Link |
|---|---|---|---|---|
| 1 | openwrt/openwrt | `docs/upstream/0001-build-make-the-EROFS-compression-selectable.patch` | Prepared, not submitted (awaiting approval) | — |
| 2 | openwrt/openwrt | `docs/upstream/0002-config-kernel-add-F2FS-compression-options.patch` | Prepared, not submitted (awaiting approval) | — |
| 3 | qemu/qemu | `patches/qemu/0001-hw-sd-sdhci-pci-migrate-the-PCI-device-state.patch` | Carried in `flake.nix`; not submitted (awaiting approval) | — |

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
