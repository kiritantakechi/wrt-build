# Patches

Every patch the project carries or prepares is a file in the repository:
- `patches/openwrt`, `patches/packages` and `patches/luci`: the series applied to the sources (`just patch`);
- `patches/qemu`: QEMU's, built into the emulator (`flake.nix`);
- `feed/*/*/patches`: the feed packages' own, applied by OpenWrt as it builds them;
- `docs/upstream`: prepared for upstream, not carried.

Nothing is submitted upstream, as a pull request, an issue or a mail, without the maintainer's consent. The patches meant for upstream are prepared here; whether and when to submit them is the maintainer's decision.

## Upstream status

Every patch file states its upstream status in an `Upstream-Status` trailer, in OpenEmbedded's vocabulary, which Buildroot follows as well:

| Status | Meaning |
|---|---|
| `Pending` | Meant for upstream, not submitted |
| `Submitted [<where>]` | Submitted, under review: the pull request or the mail |
| `Backport [<source>]` | Taken from upstream or another primary source |
| `Inappropriate [<reason>]` | Specific to this project |

In a patch made by `git format-patch`, the trailer ends the message, before the `---` line, where `git interpret-trailers --parse` reads it. A plain diff carries it in its header, before the first `diff`. The status lives in the patch, so a patch that moves or goes takes its status along, and no list elsewhere can drift from the files.

A patch's number is its identity. A dropped patch leaves its number unused, no patch is renumbered, and a new patch takes the next free number, so that a number in a message, a document or a test always means the same patch.

Every `Pending` and `Submitted` patch has a write-up below, which names its file; every write-up names a patch that exists. `tests/build/test_upstream_pinning.py` checks the trailers and holds the two in step.

## Patches meant for upstream

### EROFS compression algorithm

Patch: `docs/upstream/0001-build-make-the-EROFS-compression-selectable.patch`, for openwrt/openwrt.

Problem: `include/image.mk:110` tests `CONFIG_EROFS_FS_ZIP_LZMA`, but that symbol does not exist; the Kconfig option is named `KERNEL_EROFS_FS_ZIP_LZMA`. So the LZMA branch never runs, and every EROFS image is in fact compressed with lz4hc.

Why a rename alone is not enough: `KERNEL_EROFS_FS_ZIP_LZMA` has no prompt and defaults to y when EROFS is enabled. With only the rename, every EROFS build would **silently switch to LZMA**, and this project's images would change with it, whereas we chose lz4hc.

What the patch does: it adds a `compression` choice that defaults to lz4hc, matching the current actual behavior; choosing LZMA also selects the kernel's LZMA support. `image.mk` now tests this choice instead.

### Kernel options for F2FS compression

Patch: `docs/upstream/0002-config-kernel-add-F2FS-compression-options.patch`, for openwrt/openwrt.

Problem: fstools can format the overlay as compressed f2fs via `fstools_overlay_compression_type=`, but `config/Config-kernel.in` has no matching `KERNEL_F2FS_*` options, so the build configuration cannot select them.

What the patch does: it adds `KERNEL_F2FS_FS_COMPRESSION` and each algorithm option beneath it (LZO, LZO-RLE, LZ4, LZ4HC, ZSTD). The kernel defaults all of these options to y, and if any of them has no value the build stops, so each one needs a matching `KERNEL_*`. F2FS selects the libraries of the algorithms it compresses with, which are modules when f2fs is one, so `kmod-fs-f2fs` depends on the kmods that hold them (`kmod-lib-lzo`, `kmod-lib-lz4`, `kmod-lib-lz4hc`, `kmod-lib-zstd`), each under its option.

How this project handles it: it does not depend on this patch; instead, the upstream-native kernel config overlay (`config/kernel.config` → `env/kernel-config`) provides the same options. Once upstream accepts the patch, we can switch back to `CONFIG_KERNEL_F2FS_*` in the seed.

Verification log: 2026-09-28, this patch and the EROFS one above apply cleanly with `git am` onto openwrt `1019293`, as pinned by the lock.

2026-10-05: on `1019293`, `make defconfig` for the NanoPi R4S with `kmod-fs-f2fs` as a module and `KERNEL_F2FS_FS_COMPRESSION` selects `kmod-lib-lz4` and `kmod-lib-zstd`, the algorithms on by default, and neither LZO's nor LZ4HC's kmod. Before submitting: build f2fs as a module with every algorithm on and check that `f2fs.ko` loads with the selected kmods (this project builds F2FS into the kernel).

### sdhci-pci loses its card on loadvm (QEMU)

Patch: `patches/qemu/0001-hw-sd-sdhci-pci-migrate-the-PCI-device-state.patch`, for qemu/qemu.

Problem: `sdhci-pci` takes the migration description of the sysbus SDHCI variants, `sdhci_vmstate`, which holds only the controller registers. Its PCI configuration space is never saved, so after `loadvm` (or a migration) the BAR is unmapped, every register reads as all ones, and the guest loses its card ("Controller never released inhibit bit(s)").

Why it matters here: since r4s-ab-rollback, the emulator boots the factory image from its boot disk, an SD card or an eMMC on `sdhci-pci`, and the tests return the machine to a `savevm` snapshot between every two tests.

What the patch does: it gives `sdhci-pci` a description of its own: the PCI device state first, then the shared controller state. Its migration section is then named `sdhci-pci` rather than `sdhci`, so a stream from an earlier QEMU no longer loads into `sdhci-pci`; such a stream holds no PCI state, and its guest lost the card anyway. `flake.nix` builds the emulator's QEMU (aarch64 guests only) with it, and with every other patch in `patches/qemu/`.

Verification log: 2026-09-29, QEMU 11.1.1 builds with the patch, and the emulation tests, which restore a snapshot between every two tests, pass with the SD card.

### einat marks the inbound packets it translates back

Patch: `feed/net/einat/patches/100-mark-inbound-packets-translated-back.patch`, for EHfive/einat-ebpf.

Problem: einat reverse-translates inbound packets in its tc ingress program, before netfilter sees them, and leaves no trace of having done so. A firewall behind it cannot tell a packet einat let in (a reply, or a new flow to a mapped port under full-cone filtering) from one that arrived for an internal address by other means (a spoofed destination). The usual answer, accepting every forwarded packet from the external zone towards the internal ones, accepts both.

What the patch does: an `inbound_mark` option (`--inbound-mark` on the command line), ORed into `skb->mark` by `ingress_rev_snat` after a successful reverse translation. It is a read-only global of the BPF object, 0 by default, which marks nothing, so without the option einat behaves as before. Hairpinned packets never pass `ingress_rev_snat` (egress redirects them), so they stay unmarked. The Rust side adds the option to the configuration and the command line (hexadecimal accepted) and passes it with the other globals; the rodata struct gains explicit padding, as the loader requires a layout without implicit padding.

How this project uses it: einat runs with `--inbound-mark 0x20000000` (the bit `config/marks.tsv` gives it), and its init script adds one fw4 rule that accepts forwarded packets from wan to lan carrying the bit (r4s-ebpf-datapath design D2, D3).

Verification log: 2026-09-29, the patch applies to einat-ebpf 0.1.11 (`ba647ce`) and builds with the aya loader.

### qosify stays unconfigured after a slow start

Patch: `patches/openwrt/0006-qosify-configure-the-daemon-whenever-it-comes-up.patch`, for openwrt/openwrt.

Problem: qosify's init script waits 10 seconds for the daemon's ubus object and, if it has not appeared by then, gives up on configuring it: no shaping and no classification until the next reload, with only "Command failed: Request timed out" in the log. The daemon registers once its BPF programs are loaded, which on a busy boot takes longer; the emulator hit it on every boot.

What the patch does: `service_running` waits in the background, so the boot does not wait along, for as long as procd runs the daemon, and configures it once it appears; it then returns whether procd runs the daemon, as the `running` action expects. A first version waited two minutes; with every CPU of the test VM kept busy the daemon took longer, and stayed unconfigured. `PKG_RELEASE` goes to 2.

Verification log: 2026-09-29, in the emulator qosify now attaches cake and its classifiers to pppoe-wan at boot (`tests/network/test_qos.py`, `test_tc_hook_order.py`). 2026-10-01, with every CPU of the VM kept busy, the daemon took up to three minutes to come up after a restart, and was configured every time, over eight rounds of restarts and redials.

### rockchip: IRQ affinity for every net device

Patch: `patches/openwrt/0007-rockchip-wait-for-a-NIC-s-IRQ-only-on-that-NIC-s-own.patch`, for openwrt/openwrt.

Problem: `40-net-smp-affinity` runs its whole body on every net `add` event, whatever the device: each bridge, veth or tunnel sets every NIC's IRQ affinity again and waits up to ten seconds per NIC for the IRQ to show in `/proc/interrupts`. procd runs hotplug scripts one after another, so a NIC whose IRQ carries another name (the emulator's virtio NICs) holds up every later net event: dae's own veths and a container bridge were bound minutes late.

What the patch does: `set_interface_core` waits for a NIC's IRQ only on that NIC's own event. Any other net event still sets the affinity of every NIC whose IRQ is listed already, and skips the others without waiting. A NIC's driver may request its IRQ only when the NIC is brought up, as r8169 and stmmac do, so the IRQ can appear after the NIC's own event stopped waiting: the next net device to appear then sets it, as before the patch.

Verification log: 2026-09-29, a bridge created after dae is bound within the spec's 60 seconds (`tests/network/test_transparent_proxy.py`).

2026-10-05: the script run with stand-ins for `/proc/interrupts` and `/proc/irq` (the emulator's virtio IRQs never match): a bridge's event set eth0, whose IRQ was listed, and skipped eth1, whose IRQ was not, at once; the next event set both. On the devices, the IRQs of the NICs are not checked by a test.

### ksmbd-tools: shares on a disk that is not mounted

Patch: `patches/packages/0001-ksmbd-tools-share-only-what-is-mounted-and-start-onc.patch`, for openwrt/packages.

Problem: ksmbd's init script shares every configured path whether or not the disk it belongs on is mounted. A share on a USB disk that is late or absent then shares the empty directory underneath, on the router's flash: what clients write there fills the flash, and disappears from view once the disk is mounted over it. Nothing starts the service again when the disk arrives.

What the patch does: `smb_add_share` asks `procd_get_mountpoints` for the fstab mount point a share's path lies on and leaves the share out while that mount point is not mounted; the service does not start while every share waits; `service_triggers` adds a restart mount trigger per share path, so the mount brings the share. Shares on no fstab mount point are unaffected. `PKG_RELEASE` goes to 2. A disk unmounted while the service runs keeps its shares until the service restarts: procd's mount triggers fire when a mount point is mounted, not when it is unmounted.

How this project uses it: the share `shares` lies on the data disk, whose fstab entry exists from the first boot (r4s-services D2).

Verification log: 2026-09-29, in the emulator ksmbd stays down without the data disk and starts when it is plugged in (`tests/storage/test_data_disk.py`, `tests/services/test_file_sharing.py`).

### ubox: a log file on a disk that is not mounted

Patch: `patches/openwrt/0008-ubox-log-to-a-file-only-while-its-mount-point-is-mou.patch`, for openwrt/openwrt.

Problem: the log service leaves its log file out while the file's fstab mount point is not mounted, but only at boot. A start or reload later on, such as the reload that any change to the system configuration brings, creates the directory on the root filesystem and logs there: onto the flash, underneath where the disk mounts.

What the patch does: the log file is left out whenever its mount point is not mounted; its mount trigger starts it once the mount point is mounted, as at boot. `PKG_RELEASE` goes to 2.

How this project uses it: the persistent log is `/mnt/data/logs/messages`, on the data disk (r4s-services D2).

Verification log: 2026-09-29, in the emulator the log service restarted while the data disk is absent writes nothing to the SD card, and starts writing to the disk when it is plugged in (`tests/storage/test_data_disk.py`).

### toolchain: the buildbot version check races under make -j

Patch: `patches/openwrt/0009-toolchain-check-the-version-stamp-without-a-race.patch`, for openwrt/openwrt.

Problem: in buildbot mode, every make that reads the top-level Makefile checks the toolchain's version stamp while `tmp/.build` is newer than the stamp. Each make run from the top level touches `tmp/.build`, and a stamp that names the current version is left as it is, so the check runs in every one of these makes. Under `-j`, world starts several at once (those for `package/cleanup` and `target/compile`), and each writes the version to the same file, `tmp/.ver_check`, before comparing that file with the stamp. When one truncates the file while another compares it, the other sees a different version: it deletes the toolchain along with the build and staging directories, restarts, and the build fails for want of a compiler ("Could not find compiler").

Why it matters here: the release profile builds in buildbot mode, on a toolchain unpacked from the cache, whose stamp is older than `tmp/.build` from the first make on. A CI run lost the R4S firmware job this way (run 36736937629), while the R6S job of the same run, on the same toolchain, got through.

What the patch does: the version is kept in a shell variable instead of `tmp/.ver_check`, so concurrent checks share no file. A stamp of another version still deletes the toolchain and the build and staging directories, as before, and a failing git still stops the build.

Verification log: 2026-10-01, eight makes started a millisecond apart delete the toolchain in 38 of 40 rounds with the upstream check and in none with the patch; `tests/build/test_boards.py` ("Check the version from parallel makes") runs the patched check this way.

### qosify: an interface on a replaced device

Patch: `patches/openwrt/0010-qosify-start-an-interface-anew-on-a-replaced-device.patch` (adds the package patch `100-interface-start-an-interface-anew-on-a-replaced-device.patch`), for git.openwrt.org/project/qosify.

Problem: qosify sets an interface up on its device once, and takes it as set up for as long as it finds the interface up on a device of that name. pppoe-wan is a new device for every PPP session. When one session ends and the next starts before qosify handles the hotplug events (they run one after another, and a busy router runs them late), qosify finds the interface up on "pppoe-wan" again and leaves it be: the new device has neither the cake qdisc nor the classifiers, and nothing is shaped or classified until the interface goes down again.

Why it matters here: the emulator hit it after a redial, in CI (run 36793323171) and locally with every CPU of the VM kept busy, where `ubus call qosify status` showed `wan` active on pppoe-wan while the device carried only its default qdisc.

What the patch does: a package patch for qosify remembers the index of the device an interface was set up on, and starts the interface anew when its device has another name or another index. Upstream, it belongs to the qosify repository rather than to openwrt.git; the OpenWrt patch carries it until then. `PKG_RELEASE` goes to 3.

Verification log: 2026-10-01, with every CPU of the VM kept busy, the second redial without the patch left pppoe-wan without qosify; with it, eight rounds of restarts and redials left einat and qosify on pppoe-wan every time, 14 to 28 s after the session came up.

### build: stamps that hold across checkouts and follow the flags

Patch: `patches/openwrt/0011-build-name-prepared-stamps-after-content-and-the-tar.patch`, for openwrt/openwrt.

Problem: the prepared stamps of packages and of the kernel are named after a hash of their files, which covers the files' modification times unless `CONFIG_AUTOREMOVE` is set. Another checkout of the same sources gives every file a new time, and with it every stamp a new name: a host package built in one checkout is prepared and built again in the other. And no stamp names the flags the packages are compiled with: changing `CONFIG_TARGET_OPTIMIZATION` or `CONFIG_EXTRA_OPTIMIZATION` rebuilds nothing, and every package keeps its objects of the old flags.

Why it matters here: CI's host job packs Go's and Rust's host builds with their stamps, and each firmware job unpacks them into a fresh checkout (build-acceleration D4); with times in the stamps' names, every firmware job would build Rust again, for hours. And toolchain-o3 changes the target's flags, which the packages of a tree's earlier builds would otherwise keep.

What the patch does: the prepared stamps of packages (`PKG_FILES_MD5`) and of the kernel always hash content, as `CONFIG_AUTOREMOVE` builds already do. A host build's `rdep` looks only for files newer than its stamp, so an edit, or a touch to force a rebuild, still rebuilds, and a checkout of the same content does not. A target package and the kernel still prepare again when a file's time changes, as their `rdep` under `CONFIG_AUTOREBUILD` also compares a list of the files' times (`.dep_files`); the patch leaves that as it is, and a build with nothing changed keeps their times instead (`scripts/patch.sh` moves the tree in one checkout). Each target package's prepared stamp also hashes the symbols of the optimization flags `TARGET_CFLAGS` starts with (`TARGET_FLAGS_DEPENDS` in `rules.mk`: `CONFIG_TARGET_OPTIMIZATION`, `CONFIG_DEBUG`, `CONFIG_EXTRA_OPTIMIZATION`), so a package prepared with other flags is prepared, and so built, anew. A configured stamp would not do: configuring again keeps the build directory, and with it most of a package's objects. The kernel needs no such stamp, as Kbuild compares every object's command line.

Verification log: 2026-10-04, on the VM. With every file of the packages feed's `lang/golang` set to 2020, Go's host build prepared nothing again: its prepared stamp kept the name of its files' content, where the former name, of their paths and times, changed. Dropping `-fno-plt` from `config/toolchain.seed` prepared all 132 target packages of the R4S again, and neither the kernel nor the host builds; restoring it, the same 132. A first try with `-g0` failed in the kernel, which takes `CONFIG_EXTRA_OPTIMIZATION`, all but `-fno-plt`, as its `KCFLAGS`: without debug information, its modules' BTF could not be made.

### kernel: the modules pass up to date past the image pass

Patch: `patches/openwrt/0012-kernel-keep-the-modules-pass-up-to-date-past-the-ima.patch`, for openwrt/openwrt.

Problem: `Kernel/Make` skips kbuild when its command line is the one of its last run and no file of the kernel tree is newer than that run's stamp. The image pass runs after the modules pass and writes `vmlinux.symvers`, which modpost writes whenever it links `vmlinux` alone. The next build's modules pass finds that file newer than its stamp and runs kbuild, which removes `vmlinux` and `System.map` first and so links the kernel again, BTF included; the image pass then runs again in turn. No build ever skips kbuild.

Why it matters here: a build with nothing changed linked the kernel again in 6.5 of its minutes (5:45 for the modules pass, 0:43 for the image pass, on the VM; build-acceleration, task 2.4).

What the patch does: once the image pass has run, it refreshes the modules pass's stamp, if that pass was up to date before it. The image pass builds on what the modules pass built and changes none of its inputs, so that pass is still up to date. Whether it was is the scan that `Kernel/Make` skips by, now `Kernel/Newer`: a file of the kernel tree, the toolchain or the pass's inputs newer than the stamp, such as a module's source edited before only the image is built (`make target/linux/install`), leaves the stamp as it is, for the next modules pass to build.

Verification log: 2026-10-04, on the VM: the first build with the patch ran the modules pass once more; every later build with nothing changed skipped kbuild in both passes, in 2.5 s.

2026-10-05, on the VM, with the stamp refreshed only if it was up to date: a build of the R4S with nothing changed in the kernel skipped kbuild in both passes, and refreshed the modules pass's stamp. With `net/sched/act_csum.c` touched, `make target/linux/install` linked the kernel again and left that stamp as it was; `make target/linux/compile` then built `act_csum.ko` again.

### download: a package's source only has to be there

Patch: `patches/openwrt/0013-download-depend-on-a-package-s-source-only-being-the.patch`, for openwrt/openwrt.

Problem: a package's prepared stamp depends on every file the package downloads (`DOWNLOAD_RDEP` in `include/download.mk`), by modification time. A download that lands after the stamp, in a fresh download directory or in a tree whose build directories a cache restored, makes make prepare the package again, although the file is the one the package's hash names.

Why it matters here: CI's firmware jobs restore the toolchain, whose stamps include the host builds of Go and Rust, before `make download` runs. On 2026-10-04 main's first run after its download cache was gone (run 37220393208) downloaded Go's and Rust's sources after the restore, built both host toolchains again in each board's job, and failed the check that a board's build compiles no part of the toolchain.

What the patch does: the download becomes an order-only prerequisite of the stamps. The stamp's name covers the package's files, its Makefile among them, which names each download and its hash, so another source still gets another stamp; and a missing download is still fetched before the package is prepared.

Verification log: 2026-10-05, on the VM. With Go's source made newer than its host build's prepared stamp, Go's host build was prepared and built again without the patch (382 s), and was up to date with it (8 s).

### ppp: a PPPoE service name's length checked before it is truncated

Patch: `patches/openwrt/0014-ppp-pppoe-check-a-service-name-s-length-before-trunc.patch` (adds the package patch `209-pppoe-check-a-service-name-s-length-before-truncating-it.patch`), for github.com/ppp-project/ppp.

Problem: pppd's PPPoE plugin truncates the service name's length to the 16 bits of its tag before `sendPADI` and `sendPADR` check the room the tag takes in the packet. A name of 65532 bytes or more makes the tag's length wrap and passes the check, and the name overflows the 1528-byte packet on the stack: `sendPADI` copies all of it, `sendPADR` up to 65535 bytes. The name comes from the `rp_pppoe_service` option (UCI's `service`), which takes a string of any length. ppp's master and 2.5.4 have the same code.

Why it matters here: `pppoe.so` dials the WAN of every image. Only root sets the name, but an overflow of a stack buffer is undefined behavior that `-O3` is free to exploit, and the review of the build's warnings (docs/undefined-behavior.md) found it next to the lines GCC flagged.

What the patch does: both functions check the room with the untruncated length, so a name that does not fit fails discovery with "Would create too-long packet", as any other tag that does not fit does; `sendPADI` copies as many bytes as the tag states.

### crun: an update's JSON checked before it is used

Patch: `patches/packages/0003-crun-check-the-generated-JSON-before-using-it.patch` (adds the package patch `100-update-check-the-generated-JSON-before-using-it.patch`), for github.com/containers/crun.

Problem: `libcrun_container_update_from_values`, which `crun update` runs, ignores the status of `json_gen_get_buf`. When json-c cannot allocate the document or its text, the buffer stays unset, and the indeterminate pointer is parsed as the update's JSON. crun's other callers of `json_gen_get_buf` check the status; crun's main has the same code (2026-10-05).

Why it matters here: `podman update` runs `crun update` for the containers of wrt-containers, and a router runs out of memory more readily than a server. The review of the build's warnings found it (`'buf' may be used uninitialized`).

What the patch does: the update fails with an error, after freeing the generator, as the other callers do.

### bash: six places of undefined behavior

Patch: `patches/packages/0004-bash-fix-the-undefined-behavior-of-six-places.patch` (adds the package patches `100` to `105`), for bash (bug-bash@gnu.org, git.savannah.gnu.org/git/bash.git).

Problem: the review of bash 5.3's warnings at `-O3` (docs/undefined-behavior.md) found five faults behind them and one next to them, none fixed in bash's devel branch (1c20880e, 2026-09-23):
- `make_command` clears every command's flags through a `SIMPLE_COM` pointer, larger than the group or subshell structure it points to (`-Warray-bounds`).
- `parse_comsub` restores `extglob` from a local it never set, when parsing a command substitution changes the compatibility level, as a `PS2` that assigns `BASH_COMPAT` does.
- `array_value_internal` goes on with an array that expanding its subscript (`${ unset A; ...; }`) unset, freed or gave another type: it reads freed memory, and at `-O3` the shell crashed, or an index it never computed.
- `split_at_delims` leaves the word counts unset for a string of whitespace delimiters, and programmable completion sets `COMP_CWORD` from an indeterminate value.
- `do_redirection_internal` restores a word's flags from a variable never set, when expanding the word turns posix mode on (`${POSIXLY_CORRECT:=...}`).
- `pushd --9223372036854775808` overflows a subtraction.

Why it matters here: bash is in every image, and `-O3` is free to exploit any of them.

What the patches do: one patch per fault, each the smallest change that removes it. `array_value_internal` looks the array up again after each expansion of its subscript and expands to nothing when its type changed; `pushd` checks the offset before it subtracts. The others store what they left unset, or keep what they read twice.

Verification log: 2026-10-05, on the VM, with the R6S's `-O3` build run through the image's musl loader. The array whose subscript unsets it and makes it indexed expands to nothing, in a function and at global scope, where the unpatched shell printed another element or crashed; arrays, groups, subshells, functions, posix mode through a redirection word, and `pushd` with `--9223372036854775808` and `--1` behave as before or fail with bash's own errors. The interactive cases (`PS2`, completion) were not run.

### luci-base: the host tools built in the host build directory

Patch: `patches/luci/0001-luci-base-build-po2lmo-and-jsmin-in-the-host-build-d.patch`, for openwrt/luci.

Problem: luci-base's host build compiles `po2lmo` and `jsmin` with `make -C src/`, in the package's own source directory, after it has written its prepared stamp. Their objects and binaries are then newer than that stamp, so every build prepares luci-base again, for the host and for the target, and packages it anew.

Why it matters here: with the rest of build-acceleration, luci-base was the only package a build with nothing changed still prepared and compiled.

What the patch does: `Host/Prepare` already copies `src/` into the host build directory, so `Host/Compile` builds there, and `Host/Install` takes the tools from there.

Verification log: 2026-10-04, both tools build from a copy of `src/`, as in the host build directory, and with the patch a build with nothing changed no longer prepares luci-base.
