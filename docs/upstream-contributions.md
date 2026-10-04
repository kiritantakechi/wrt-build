# Upstream contributions

Any PR, issue or push to a repository the maintainer does not own requires explicit consent first. The patches here are only prepared locally; whether and when to submit them is up to the maintainer.

| # | Repository | Patch | Status | Link |
|---|---|---|---|---|
| 1 | openwrt/openwrt | `docs/upstream/0001-build-make-the-EROFS-compression-selectable.patch` | Prepared, not submitted (awaiting approval) | — |
| 2 | openwrt/openwrt | `docs/upstream/0002-config-kernel-add-F2FS-compression-options.patch` | Prepared, not submitted (awaiting approval) | — |
| 3 | qemu/qemu | `patches/qemu/0001-hw-sd-sdhci-pci-migrate-the-PCI-device-state.patch` | Carried in `flake.nix`; not submitted (awaiting approval) | — |
| 4 | EHfive/einat-ebpf | `feed/net/einat/patches/100-mark-inbound-packets-translated-back.patch` | Carried in the einat package; not submitted (awaiting approval) | — |
| 5 | openwrt/openwrt | `patches/openwrt/0006-qosify-configure-the-daemon-whenever-it-comes-up.patch` | Carried in the patch series; not submitted (awaiting approval) | — |
| 6 | openwrt/openwrt | `patches/openwrt/0007-rockchip-set-a-NIC-s-IRQ-affinity-only-when-that-NIC.patch` | Carried in the patch series; not submitted (awaiting approval) | — |
| 7 | openwrt/packages | `patches/packages/0001-ksmbd-tools-share-only-what-is-mounted-and-start-onc.patch` | Carried in the patch series; not submitted (awaiting approval) | — |
| 8 | openwrt/openwrt | `patches/openwrt/0008-ubox-log-to-a-file-only-while-its-mount-point-is-mou.patch` | Carried in the patch series; not submitted (awaiting approval) | — |
| 9 | openwrt/openwrt | `patches/openwrt/0009-toolchain-check-the-version-stamp-without-a-race.patch` | Carried in the patch series; not submitted (awaiting approval) | — |
| 10 | git.openwrt.org/project/qosify | `patches/openwrt/0010-qosify-start-an-interface-anew-on-a-replaced-device.patch` (adds the package patch `100-interface-start-an-interface-anew-on-a-replaced-device.patch`) | Carried in the patch series; not submitted (awaiting approval) | — |
| 11 | openwrt/openwrt | `patches/openwrt/0011-build-name-prepared-stamps-after-content-and-the-tar.patch` | Carried in the patch series; not submitted (awaiting approval) | — |
| 12 | openwrt/openwrt | `patches/openwrt/0012-kernel-keep-the-modules-pass-up-to-date-past-the-ima.patch` | Carried in the patch series; not submitted (awaiting approval) | — |
| 13 | openwrt/luci | `patches/luci/0001-luci-base-build-po2lmo-and-jsmin-in-the-host-build-d.patch` | Carried in the patch series; not submitted (awaiting approval) | — |

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

Why it matters here: since r4s-ab-rollback, the emulator boots the factory image from its boot disk, an SD card or an eMMC on `sdhci-pci`, and the tests return the machine to a `savevm` snapshot between every two tests.

What the patch does: it gives `sdhci-pci` a description of its own: the PCI device state first, then the shared controller state. `flake.nix` builds the emulator's QEMU (aarch64 guests only) with it, and with every other patch in `patches/qemu/`.

Verification log: 2026-09-29, QEMU 11.1.1 builds with the patch, and the emulation tests, which restore a snapshot between every two tests, pass with the SD card.

## 4. einat marks the inbound packets it translates back

Problem: einat reverse-translates inbound packets in its tc ingress program, before netfilter sees them, and leaves no trace of having done so. A firewall behind it cannot tell a packet einat let in (a reply, or a new flow to a mapped port under full-cone filtering) from one that arrived for an internal address by other means (a spoofed destination). The usual answer, accepting every forwarded packet from the external zone towards the internal ones, accepts both.

What the patch does: an `inbound_mark` option (`--inbound-mark` on the command line), ORed into `skb->mark` by `ingress_rev_snat` after a successful reverse translation. It is a read-only global of the BPF object, 0 by default, which marks nothing, so without the option einat behaves as before. Hairpinned packets never pass `ingress_rev_snat` (egress redirects them), so they stay unmarked. The Rust side adds the option to the configuration and the command line (hexadecimal accepted) and passes it with the other globals; the rodata struct gains explicit padding, as the loader requires a layout without implicit padding.

How this project uses it: einat runs with `--inbound-mark 0x20000000` (the bit `config/marks.tsv` gives it), and its init script adds one fw4 rule that accepts forwarded packets from wan to lan carrying the bit (r4s-ebpf-datapath design D2, D3).

Verification log: 2026-09-29, the patch applies to einat-ebpf 0.1.11 (`ba647ce`) and builds with the aya loader.

## 5. qosify stays unconfigured after a slow start

Problem: qosify's init script waits 10 seconds for the daemon's ubus object and, if it has not appeared by then, gives up on configuring it: no shaping and no classification until the next reload, with only "Command failed: Request timed out" in the log. The daemon registers once its BPF programs are loaded, which on a busy boot takes longer; the emulator hit it on every boot.

What the patch does: `service_running` waits in the background, so the boot does not wait along, for as long as procd runs the daemon, and configures it once it appears. A first version waited two minutes; with every CPU of the test VM kept busy the daemon took longer, and stayed unconfigured. `PKG_RELEASE` goes to 2.

Verification log: 2026-09-29, in the emulator qosify now attaches cake and its classifiers to pppoe-wan at boot (`tests/network/test_qos.py`, `test_tc_hook_order.py`). 2026-10-01, with every CPU of the VM kept busy, the daemon took up to three minutes to come up after a restart, and was configured every time, over eight rounds of restarts and redials.

## 6. rockchip: IRQ affinity for every net device

Problem: `40-net-smp-affinity` runs its whole body on every net `add` event, whatever the device: each bridge, veth or tunnel sets every NIC's IRQ affinity again and waits up to ten seconds per NIC for the IRQ to show in `/proc/interrupts`. procd runs hotplug scripts one after another, so a NIC whose IRQ carries another name (the emulator's virtio NICs) holds up every later net event: dae's own veths and a container bridge were bound minutes late.

What the patch does: `set_interface_core` returns unless the event is for that interface. At boot each NIC's own event still sets its affinity, so the result on the device is the same.

Verification log: 2026-09-29, a bridge created after dae is bound within the spec's 60 seconds (`tests/network/test_transparent_proxy.py`).

## 7. ksmbd-tools: shares on a disk that is not mounted

Problem: ksmbd's init script shares every configured path whether or not the disk it belongs on is mounted. A share on a USB disk that is late, absent or pulled out then shares the empty directory underneath, on the router's flash: what clients write there fills the flash, and disappears from view once the disk is mounted over it. Nothing starts the service again when the disk arrives.

What the patch does: `smb_add_share` asks `procd_get_mountpoints` for the fstab mount point a share's path lies on and leaves the share out while that mount point is not mounted; the service does not start while every share waits; `service_triggers` adds a restart mount trigger per share path, so the mount brings the share. Shares on no fstab mount point are unaffected. `PKG_RELEASE` goes to 2.

How this project uses it: the share `shares` lies on the data disk, whose fstab entry exists from the first boot (r4s-services D2).

Verification log: 2026-09-29, in the emulator ksmbd stays down without the data disk and starts when it is plugged in (`tests/storage/test_data_disk.py`, `tests/services/test_file_sharing.py`).

## 8. ubox: a log file on a disk that is not mounted

Problem: the log service leaves its log file out while the file's fstab mount point is not mounted, but only at boot. A start or reload later on, such as the reload that any change to the system configuration brings, creates the directory on the root filesystem and logs there: onto the flash, underneath where the disk mounts.

What the patch does: the log file is left out whenever its mount point is not mounted; its mount trigger starts it once the mount point is mounted, as at boot. `PKG_RELEASE` goes to 2.

How this project uses it: the persistent log is `/mnt/data/logs/messages`, on the data disk (r4s-services D2).

Verification log: 2026-09-29, in the emulator the log service restarted while the data disk is absent writes nothing to the SD card, and starts writing to the disk when it is plugged in (`tests/storage/test_data_disk.py`).

## 9. toolchain: the buildbot version check races under make -j

Problem: in buildbot mode, every make that reads the top-level Makefile checks the toolchain's version stamp while `tmp/.build` is newer than the stamp. Each make run from the top level touches `tmp/.build`, and a stamp that names the current version is left as it is, so the check runs in every one of these makes. Under `-j`, world starts several at once (those for `package/cleanup` and `target/compile`), and each writes the version to the same file, `tmp/.ver_check`, before comparing that file with the stamp. When one truncates the file while another compares it, the other sees a different version: it deletes the toolchain along with the build and staging directories, restarts, and the build fails for want of a compiler ("Could not find compiler").

Why it matters here: the release profile builds in buildbot mode, on a toolchain unpacked from the cache, whose stamp is older than `tmp/.build` from the first make on. A CI run lost the R4S firmware job this way (run 36736937629), while the R6S job of the same run, on the same toolchain, got through.

What the patch does: the version is kept in a shell variable instead of `tmp/.ver_check`, so concurrent checks share no file. A stamp of another version still deletes the toolchain and the build and staging directories, as before, and a failing git still stops the build.

Verification log: 2026-10-01, eight makes started a millisecond apart delete the toolchain in 38 of 40 rounds with the upstream check and in none with the patch; `tests/build/test_boards.py` ("Check the version from parallel makes") runs the patched check this way.

## 10. qosify: an interface on a replaced device

Problem: qosify sets an interface up on its device once, and takes it as set up for as long as it finds the interface up on a device of that name. pppoe-wan is a new device for every PPP session. When one session ends and the next starts before qosify handles the hotplug events (they run one after another, and a busy router runs them late), qosify finds the interface up on "pppoe-wan" again and leaves it be: the new device has neither the cake qdisc nor the classifiers, and nothing is shaped or classified until the interface goes down again.

Why it matters here: the emulator hit it after a redial, in CI (run 36793323171) and locally with every CPU of the VM kept busy, where `ubus call qosify status` showed `wan` active on pppoe-wan while the device carried only its default qdisc.

What the patch does: a package patch for qosify remembers the index of the device an interface was set up on, and starts the interface anew when its device has another name or another index. Upstream, it belongs to the qosify repository rather than to openwrt.git; the OpenWrt patch carries it until then. `PKG_RELEASE` goes to 3.

Verification log: 2026-10-01, with every CPU of the VM kept busy, the second redial without the patch left pppoe-wan without qosify; with it, eight rounds of restarts and redials left einat and qosify on pppoe-wan every time, 14 to 28 s after the session came up.

## 11. build: stamps that hold across checkouts and follow the flags

Problem: the prepared stamps of packages and of the kernel are named after a hash of their files, which covers the files' modification times unless `CONFIG_AUTOREMOVE` is set. A checkout that gives a file a new time and the same content makes its stamps stale: a build made in one checkout never holds in another, and re-applying a patch series prepares the kernel and every patched package again. And no stamp names the flags the packages are compiled with: changing `CONFIG_TARGET_OPTIMIZATION` or `CONFIG_EXTRA_OPTIMIZATION` rebuilds nothing, and every package keeps its objects of the old flags.

Why it matters here: `just patch` applied the series anew before every build, so a build with nothing changed took 28 minutes, 13.5 of them preparing and compiling the kernel again (`docs/dev-setup.md`). And toolchain-o3 changes the target's flags, which the packages of a tree's earlier builds would otherwise keep.

What the patch does: the prepared stamps of packages (`PKG_FILES_MD5`) and of the kernel always hash content, as `CONFIG_AUTOREMOVE` builds already do; `rdep` still compares modification times, so an edit, or a touch to force a rebuild, still rebuilds. Each target package's prepared stamp also hashes the symbols `TARGET_CFLAGS` is made of (`TARGET_FLAGS_DEPENDS` in `rules.mk`), so a package prepared with other flags is prepared, and so built, anew. A configured stamp would not do: configuring again keeps the build directory, and with it most of a package's objects. The kernel needs no such stamp, as Kbuild compares every object's command line.

Verification log: 2026-10-04, on the VM. With every file of the packages feed's `lang/golang` set to 2020, Go's host build prepared nothing again: its prepared stamp kept the name of its files' content, where the former name, of their paths and times, changed. Dropping `-fno-plt` from `config/toolchain.seed` prepared all 132 target packages of the R4S again, and neither the kernel nor the host builds; restoring it, the same 132. A first try with `-g0` failed in the kernel, which takes `CONFIG_EXTRA_OPTIMIZATION`, all but `-fno-plt`, as its `KCFLAGS`: without debug information, its modules' BTF could not be made.

## 12. kernel: the modules pass up to date past the image pass

Problem: `Kernel/Make` skips kbuild when its command line is the one of its last run and no file of the kernel tree is newer than that run's stamp. The image pass runs after the modules pass and writes `vmlinux.symvers`, which modpost writes whenever it links `vmlinux` alone. The next build's modules pass finds that file newer than its stamp and runs kbuild, which removes `vmlinux` and `System.map` first and so links the kernel again, BTF included; the image pass then runs again in turn. No build ever skips kbuild.

Why it matters here: a build with nothing changed linked the kernel again in 6.5 of its minutes (5:45 for the modules pass, 0:43 for the image pass, on the VM; build-acceleration, task 2.4).

What the patch does: once the image pass has run, it refreshes the modules pass's stamp. The image pass builds on what the modules pass built and changes none of its inputs, so that pass is still up to date.

Verification log: 2026-10-04, on the VM: the first build with the patch ran the modules pass once more; every later build with nothing changed skipped kbuild in both passes, in 2.5 s.

## 13. luci-base: the host tools built in the host build directory

Problem: luci-base's host build compiles `po2lmo` and `jsmin` with `make -C src/`, in the package's own source directory, after it has written its prepared stamp. Their objects and binaries are then newer than that stamp, so every build prepares luci-base again, for the host and for the target, and packages it anew.

Why it matters here: with the rest of build-acceleration, luci-base was the only package a build with nothing changed still prepared and compiled.

What the patch does: `Host/Prepare` already copies `src/` into the host build directory, so `Host/Compile` builds there, and `Host/Install` takes the tools from there.

Verification log: 2026-10-04, both tools build from a copy of `src/`, as in the host build directory, and with the patch a build with nothing changed no longer prepares luci-base.

