# Patches

Every patch the project carries or prepares is a file in the repository:
- `patches/openwrt`, `patches/packages` and `patches/luci`: the series applied to the sources (`just patch`);
- `patches/qemu`: QEMU's, built into the emulator (`flake.nix`);
- `feed/*/*/patches`: the feed packages' own, applied by OpenWrt as it builds them;
- `docs/upstream`: prepared for upstream, not carried.

Nothing is submitted upstream, as a pull request, an issue or a mail, without the maintainer's consent. The patches meant for upstream are prepared here; whether and when to submit them is the maintainer's decision.

## What a patch fixes

A patch fixes a fault where it lies, in the component whose code is wrong: a package, a tool such as the linker, or the compiler. It does so in a form that component's upstream could take, and it does not trade generality away to suit this project: it does not turn a feature off, narrow a mode, serialize work or stand in for a missing part, and it keeps working every configuration upstream supports (a fallback for older kernels, the old path for upstream's images). A patch to a tool or to the toolchain is a file in OpenWrt's `tools/<tool>/patches` or `toolchain/<component>/patches-*`, added by a patch of the series. When a general fix replaces a workaround, the workaround goes in the same step.

`Inappropriate` is for what only exists in this project, such as its A/B slot layout and its boards' images.

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

2026-10-05, with `service_running` returning whether procd runs the daemon: `tests/network/test_qos.py` and `test_tc_hook_order.py` pass on both boards' `-O3` builds.

### rockchip: IRQ affinity for every net device

Patch: `patches/openwrt/0007-rockchip-wait-for-a-NIC-s-IRQ-only-on-that-NIC-s-own.patch`, for openwrt/openwrt.

Problem: `40-net-smp-affinity` runs its whole body on every net `add` event, whatever the device: each bridge, veth or tunnel sets every NIC's IRQ affinity again and waits up to ten seconds per NIC for the IRQ to show in `/proc/interrupts`. procd runs hotplug scripts one after another, so a NIC whose IRQ carries another name (the emulator's virtio NICs) holds up every later net event: dae's own veths and a container bridge were bound minutes late.

What the patch does: `set_interface_core` waits for a NIC's IRQ only on that NIC's own event. Any other net event still sets the affinity of every NIC whose IRQ is listed already, and skips the others without waiting. A NIC's driver may request its IRQ only when the NIC is brought up, as r8169 and stmmac do, so the IRQ can appear after the NIC's own event stopped waiting: the next net device to appear then sets it, as before the patch.

Verification log: 2026-09-29, a bridge created after dae is bound within the spec's 60 seconds (`tests/network/test_transparent_proxy.py`).

2026-10-05: the script run with stand-ins for `/proc/interrupts` and `/proc/irq` (the emulator's virtio IRQs never match): a bridge's event set eth0, whose IRQ was listed, and skipped eth1, whose IRQ was not, at once; the next event set both. On the devices, the IRQs of the NICs are not checked by a test.

### ksmbd-tools: shares on a disk that is not mounted

Patch: `patches/packages/0001-ksmbd-tools-share-only-what-is-mounted-and-start-onc.patch`, for openwrt/packages.

Problem: ksmbd's init script shares every configured path whether or not the disk it belongs on is mounted. A share on a USB disk that is late or absent then shares the empty directory underneath, on the router's flash: what clients write there fills the flash, and disappears from view once the disk is mounted over it. Nothing starts the service again when the disk arrives, and nothing withdraws a share whose disk is unmounted while the service runs.

What the patch does: `smb_add_share` asks `procd_get_mountpoints` for the fstab mount point a share's path lies on and leaves the share out while that mount point is not mounted. `service_triggers` adds a reload trigger per share path for the mount, and one for the unmount (procd's unmount helpers, patch 0035), so the mount brings the share and the unmount takes it away. A reload starts the service anew, as every start resets the server hard; a restart would drop the service, and its triggers with it, until it had started again, so a disk back within that time went unnoticed. A start with every share waiting stops a running server, after that hard reset, and starts nothing. Shares on no fstab mount point are unaffected. `PKG_RELEASE` goes to 3.

How this project uses it: the share `shares` lies on the data disk, whose fstab entry exists from the first boot (r4s-services D2).

Verification log: 2026-09-29, in the emulator ksmbd stays down without the data disk and starts when it is plugged in (`tests/storage/test_data_disk.py`, `tests/services/test_file_sharing.py`). With patches 0035 and 0036, the data disk removed while the service runs stops it, port 445 included, and its return brings the shares back (the file-sharing test "Data disk removed while sharing", both boards).

### ubox: a log file on a disk that is not mounted

Patch: `patches/openwrt/0008-ubox-log-to-a-file-only-while-its-mount-point-is-mou.patch`, for openwrt/openwrt.

Problem: the log service leaves its log file out while the file's fstab mount point is not mounted, but only at boot. A start or reload later on, such as the reload that any change to the system configuration brings, creates the directory on the root filesystem and logs there: onto the flash, underneath where the disk mounts.

What the patch does: the log file is left out whenever its mount point is not mounted; its mount trigger starts it once the mount point is mounted, as at boot. `PKG_RELEASE` goes to 2.

How this project uses it: the persistent log is `/mnt/data/logs/messages`, on the data disk (r4s-services D2).

Verification log: 2026-09-29, in the emulator the log service restarted while the data disk is absent writes nothing to the SD card, and starts writing to the disk when it is plugged in (`tests/storage/test_data_disk.py`).

2026-10-05, without `boot()`: `tests/storage/test_data_disk.py` passes on both boards' `-O3` builds.

### toolchain: the buildbot version check races under make -j

Patch: `patches/openwrt/0009-toolchain-check-the-version-stamp-without-a-race.patch`, for openwrt/openwrt.

Problem: in buildbot mode, every make that reads the top-level Makefile checks the toolchain's version stamp while `tmp/.build` is newer than the stamp. Each make run from the top level touches `tmp/.build`, and a stamp that names the current version is left as it is, so the check runs in every one of these makes. Under `-j`, world starts several at once (those for `package/cleanup` and `target/compile`), and each writes the version to the same file, `tmp/.ver_check`, before comparing that file with the stamp. When one truncates the file while another compares it, the other sees a different version: it deletes the toolchain along with the build and staging directories, restarts, and the build fails for want of a compiler ("Could not find compiler").

Why it matters here: the release profile builds in buildbot mode, on a toolchain unpacked from the cache, whose stamp is older than `tmp/.build` from the first make on. A CI run lost the R4S firmware job this way (run 36736937629), while the R6S job of the same run, on the same toolchain, got through.

What the patch does: the version is kept in a shell variable instead of `tmp/.ver_check`, so concurrent checks share no file. A stamp of another version still deletes the toolchain and the build and staging directories, as before, and a failing git still stops the build.

Verification log: 2026-10-01, eight makes started a millisecond apart delete the toolchain in 38 of 40 rounds with the upstream check and in none with the patch; `tests/build/test_boards.py` ("Check the version from parallel makes") runs the patched check this way.

Patch 0038 keeps this form of the check, and makes it record the toolchain's content in every mode.

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

### build: each job's output whole in a package's log

Patch: `patches/openwrt/0016-build-write-each-job-s-output-whole-to-a-package-s-l.patch`, for openwrt/openwrt.

Problem: a package built in parallel runs its jobs beside each other, and each compiler writes its diagnostics to the package's log as it goes. A diagnostic is written in pieces, its "In function" context and its chain of inlined calls apart from the message, so the pieces of jobs running at once interleave: a warning follows another job's context, and a reader of the log places it in the wrong function or in none.

Why it matters here: the build reports the UB-indicative warnings of each package from its log, by function (`docs/undefined-behavior.md`). bash's warnings were placed in different functions on the two boards.

What the patch does: a parallel package's make runs with `--output-sync=target`, which writes each job's output once the job ends. The jobs still run in parallel under the build's jobserver; only their output is held back. Make passes the option on to the makes it starts, among them the one GCC runs for a link's LTO jobs under the jobserver.

Verification log: 2026-10-05, on the VM: the make that GCC ran for bash's LTRANS jobs had `-Otarget` and the build's output-sync mutex in its `MAKEFLAGS`, and no log of either board's build held a diagnostic cut by another job's output.

### build: sanitizers at the link

Patch: `patches/openwrt/0017-build-link-with-the-sanitizers-the-packages-are-comp.patch`, for openwrt/openwrt.

Problem: a sanitizer is a link option too: the link adds the sanitizer's runtime, or with `-fsanitize-trap` leaves it out, and under LTO GCC expands the checks only at the link, as traps or as calls into the runtime, by the options on the link line (lto-wrapper passes no sanitizer option on from the objects). Packages compile with `TARGET_CFLAGS`, but many link with `TARGET_LDFLAGS` alone, as make's built-in rule and meson do.

Why it matters here: the `ubsan` profile (`docs/undefined-behavior.md`) compiles every package with `-fsanitize=undefined -fsanitize-trap=undefined`. mtd and glib2, which use LTO, linked their checks as calls into libubsan, which OpenWrt's musl toolchain does not have.

What the patch does: `include/package.mk` adds the sanitizer options of `TARGET_CFLAGS` to `TARGET_LDFLAGS`. A build without sanitizers is unchanged.

Verification log: 2026-10-06, on the VM, in the R4S's `ubsan` tree: without the patch, mtd's link failed on undefined `__ubsan_handle_add_overflow` and `__ubsan_handle_sub_overflow`, and glib2's on four; with it, mtd linked with no call into the runtime and 264 trap instructions.

### mold: LTO objects claimed in the command line order

Patch: `patches/openwrt/0018-tools-mold-claim-LTO-objects-in-the-command-line-ord.patch` (adds the mold patch `tools/mold/patches/001-claim-lto-objects-in-the-command-line-order.patch`), for rui314/mold, carried by openwrt/openwrt until then.

Problem: mold reads input files in parallel, and its reader threads called the LTO plugin's claim hook for each LTO object as they reached it, one at a time under a mutex. GCC's plugin hands the objects to the compiler in the order it claimed them, and what LTO makes depends on that order: a link with LTO and mold is not reproducible, and the warnings GCC gives while linking come and go.

Why it matters here: both boards build with LTO and mold (`config/toolchain.seed`). jansson's three warnings appeared in some builds of a board and not in others, locally and in CI (runs 37293958173 and 37324813891), so the register's reviews of them were now unmatched, now missing.

What the patch does: mold records the LTO objects while it reads, and claims them once all input files and linker scripts are read, one at a time and in the command line order, as it already parses linker scripts after the parallel read. The files are still read in parallel; links of the same objects give the same output, as they do with GNU ld. Upstream, the patch belongs to mold.

Verification log: 2026-10-06, on the VM, mold 2.42.0: six links of jansson's library from the same objects gave six different libraries without the patch, and the overflow warnings in some of them only; with the patch, with mold's threads, the six gave the same library, the one GNU ld gives, and the three warnings each time.

### libtool: every sanitizer option passed to the link

Patch: `patches/openwrt/0019-tools-libtool-pass-every-sanitizer-option-through-to.patch` (adds the libtool patch `tools/libtool/patches/150-pass-every-sanitizer-option-through-to-the-link.patch`), for GNU libtool, carried by openwrt/openwrt until then.

Problem: libtool passes `-fsanitize=*` to the compiler driver that links, but drops the sanitizers' other options, `-fsanitize-trap=*` and `-fsanitize-recover=*` among them. Those decide what the link does: with `-fsanitize=undefined` alone GCC links libubsan, while with `-fsanitize-trap=undefined` too it needs no runtime; and under LTO GCC expands the checks at the link by the options on its line.

Why it matters here: in the `ubsan` profile, libmd, libmnl and musl-fts failed to link for want of a libubsan the toolchain does not have, and `libnftnl.so`, which uses LTO, linked five calls into it.

What the patch does: libtool passes every option that starts with `-fsanitize` through, as it already does those that start with `-fno-sanitize`. Upstream, the patch belongs to libtool's `build-aux/ltmain.in`.

Verification log: 2026-10-06, on the VM: libmd, libmnl and musl-fts linked under LTO with `-fsanitize-trap` and no call into a runtime once their libtool passed every sanitizer option (patch 0021 gives their own copies this patch's change).

### build: the sanitizer options through the packages' libtool

Patch: `patches/openwrt/0021-build-pass-the-sanitizer-options-through-the-package.patch`, for openwrt/openwrt.

Problem: most packages built with autotools carry their own copy of libtool, which passes `-fsanitize=` to the link but drops the sanitizers' other options, `-fsanitize-trap` among them. Patch 0019 fixes libtool itself, but reaches only the packages that OpenWrt regenerates with its own libtool, those that ask for the libtool fixup.

Why it matters here: in the `ubsan` profile, libmd, libmnl and musl-fts, among others, failed to link for want of libubsan.

What the patch does: in a build whose `TARGET_CFLAGS` sanitize, every `ltmain.sh` a package carries gets `-fsanitize*` among the options it passes through, before the package is configured, as the build's own libtool has it. The line it extends is the same in every libtool from 2.2 to 2.5, and a copy without it stops the build. Regenerating the packages' build systems with the build's libtool, tried first, broke libffi's build directories. A build without sanitizers is unchanged.

Verification log: 2026-10-06, on the VM, in the R4S's `ubsan` tree: the 27 copies of libtool in the R4S's packages, 2.2.7a to 2.5.4, all have the line. libffi (libtool 2.4.7), libmd, libmnl and musl-fts linked under LTO with no call into a runtime and 4,909, 1,290, 92 and 222 trap instructions.

### gcc: each LTRANS job's output whole

Patch: `patches/openwrt/0020-toolchain-gcc-write-each-LTRANS-job-s-output-whole.patch` (adds the GCC patch `toolchain/gcc/patches-15.x/990-lto-wrapper-write-each-LTRANS-job-s-output-whole.patch`), for GCC, carried by openwrt/openwrt until then.

Problem: when lto-wrapper runs a link's LTRANS jobs in parallel through make, the jobs write their diagnostics to the same stream as they go, in pieces, and those of jobs running at once interleave. Under a jobserver the make inherits the build's flags, but a package built without one has lto-wrapper start make with a number of jobs of its own (`-flto=auto`) and no flags from above.

Why it matters here: the warnings of such a package's link would be placed in the wrong function, as bash's were before patch 0016. Running those jobs one after another (`-flto=1`) would have avoided it by giving up their parallelism.

What the patch does: lto-wrapper runs its make with `--output-sync=target`, so each job's output is written whole once the job ends, and the jobs keep running in parallel. GNU make has had the option since 4.0, and lto-wrapper already needs GNU make to run LTRANS in parallel.

Verification log: see the builds of both boards in `docs/undefined-behavior.md` and `docs/ci.md`.

### busybox: printf without arithmetic on a null pointer

Patch: `patches/openwrt/0022-busybox-printf-no-arithmetic-on-a-null-pointer.patch` (adds the busybox patch `package/utils/busybox/patches/800-printf-do-not-subtract-from-a-null-pointer.patch`), for busybox, carried by openwrt/openwrt until then.

Problem: `print_direc()` tells a `*` for the width from the one of `.*` by comparing the place of the first `*` less one with that of `.*`. In a conversion without a `*`, `strchr()` returns NULL, and the comparison subtracts one from a null pointer, which is undefined behavior.

Why it matters here: the `ubsan` profile's first run (`docs/undefined-behavior.md`) trapped here: 384 traps during one boot, in every init script and tool that runs printf, the log service's and the health check's among them.

What the patch does: it compares only when the conversion has a `*`.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### ubox: logd's entries aligned

Patch: `patches/openwrt/0023-ubox-logd-align-each-log-entry-to-the-header-that-fo.patch` (adds the ubox patch `package/system/ubox/patches/100-logd-align-each-log-entry-to-the-header-that-follows-it.patch`), for git.openwrt.org/project/ubox, carried by openwrt/openwrt until then.

Problem: logd's entries follow each other in its buffer, each a `struct log_head` and its message, padded to four bytes. The header holds a `struct timespec`, which needs eight-byte alignment on 64-bit targets, so after a message whose padded length is four more than a multiple of eight the next header is misaligned, and reading it is undefined behavior.

Why it matters here: the `ubsan` profile's first run (`docs/undefined-behavior.md`) trapped here: logd trapped in `log_next()` within seconds of booting.

What the patch does: each entry is padded to the alignment of `struct log_head`.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### ubox: logd's log copied into the new buffer

Patch: `patches/openwrt/0024-ubox-logd-copy-the-log-into-the-new-buffer-when-it-g.patch` (adds the ubox patch `package/system/ubox/patches/101-logd-advance-in-the-new-buffer-when-it-copies-the-log.patch`), for git.openwrt.org/project/ubox, carried by openwrt/openwrt until then.

Problem: when the log buffer grows, `log_buffer_init()` copies the entries into the new buffer, but moves the destination past each copy by the old entry's size from the old entry's address. From the second entry on it copies into the old buffer, frees that buffer, and leaves `newest` pointing into it.

Why it matters here: found while reading `log_buffer_init()` for patch 0023. A change of the system's log size grows the buffer at run time.

What the patch does: it moves past each copy in the new buffer.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### libubox: 64-bit integers formatted without assuming alignment

Patch: `patches/openwrt/0025-libubox-blobmsg_json-read-64-bit-integers-without-as.patch` (adds the libubox patch `package/libs/libubox/patches/100-blobmsg_json-read-64-bit-integers-without-assuming-alignment.patch`), for git.openwrt.org/project/libubox, carried by openwrt/openwrt until then.

Problem: blob attributes are padded to four bytes, so the data of an `INT64` attribute is only four-byte aligned, and `blobmsg_format_element()` read it with a 64-bit load, which is undefined behavior.

Why it matters here: the `ubsan` profile's first run (`docs/undefined-behavior.md`) trapped here: `ubus call` trapped printing a reply with a 64-bit value.

What the patch does: the value is read with `blobmsg_get_u64()`, two aligned 32-bit words, as the `DOUBLE` case already does through `blobmsg_get_double()`.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### netifd: container_of_safe for nodes that may be null

Patch: `patches/openwrt/0026-netifd-take-container_of_safe-of-nodes-that-may-be-n.patch` (adds the netifd patch `package/network/config/netifd/patches/100-netifd-take-container_of_safe-of-nodes-that-may-be-null.patch`), for git.openwrt.org/project/netifd, carried by openwrt/openwrt until then.

Problem: netifd's vlist update callbacks get the old or the new node as NULL when an entry is added or removed, and `interface_update_prefix()` is called with a NULL tree too. Four of them compute `container_of()` of those pointers before they look at them, which is pointer arithmetic on a null pointer.

Why it matters here: the `ubsan` profile's first run (`docs/undefined-behavior.md`) trapped here: netifd trapped adding a delegated prefix, and the network never came up, so no system test could reach the router.

What the patch does: `interface_update()`, `interface_update_proto_neighbor()`, `__interface_update_route()` and `interface_update_prefix()` use `container_of_safe()`, which keeps NULL, as the other callbacks check before they convert.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### ppp: the host name hashed without signed overflow

Patch: `patches/openwrt/0027-ppp-pppd-hash-the-host-name-without-signed-overflow.patch` (adds the ppp patch `package/network/services/ppp/patches/210-pppd-hash-the-host-name-without-signed-overflow.patch`), for ppp-project/ppp, carried by openwrt/openwrt until then.

Problem: pppd seeds its random numbers with `get_host_seed()`, which hashes the host name into an `int`, `h = h * 37 + c`, from 407. Any name longer than six characters overflows it, which is undefined behavior.

Why it matters here: with every earlier trap fixed, the `ubsan` profile's second run trapped in pppd's `magic_init()` at every start, so the WAN never came up.

What the patch does: the hash is computed in `unsigned int`, which wraps, and takes each character as an unsigned byte.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### gcc: no flexible array size without its object's initializer

Patch: `patches/openwrt/0028-toolchain-gcc-no-flexible-array-size-without-its-obj.patch` (adds the GCC patch `toolchain/gcc/patches-15.x/991-tree-no-flexible-array-size-without-its-object-s-initializer.patch`), for GCC, carried by openwrt/openwrt until then.

Problem: `component_ref_size()` takes the size of an initialized flexible array member from its object's initializer, and gives up for an extern object, whose initializer it cannot see. Under LTO, a partition other than the one that defines the object cannot see the initializer either, as `DECL_INITIAL` is `error_mark_node` there. It then took the size of the struct alone, so the member looked empty, and `-fsanitize=object-size` turned every function there that reads it into a trap.

Why it matters here: the `ubsan` profile's third run trapped in nftables' `ct_print()`, which walks a statically initialized flexible array of symbols and had become a single trap: `nft` trapped printing any rule with a ct expression. Without the object-size check, the same function compiles to its code.

What the patch does: the size is unknown when the initializer is not available, as it already is for an extern object.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### odhcp6c: no variable length array of zero IA_NA addresses

Patch: `patches/openwrt/0029-odhcp6c-no-variable-length-array-of-zero-IA_NA-addre.patch` (adds the odhcp6c patch `package/network/ipv6/odhcp6c/patches/100-dhcpv6-no-variable-length-array-of-zero-IA_NA-addresses.patch`), for git.openwrt.org/project/odhcp6c, carried by openwrt/openwrt until then.

Problem: `dhcpv6_send()` puts the IA_NA addresses in a variable length array as long as their count. That is zero until the client holds an address, and always when it asks for prefixes only, and a variable length array of length zero is undefined behavior.

Why it matters here: the `ubsan` profile's third run trapped here when odhcp6c sent its first Solicit on the WAN.

What the patch does: the addresses are allocated with `alloca()`, as the IA_PD options already are, and their length is taken from their count.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### fstools: a UUID formatted without assuming its alignment

Patch: `patches/openwrt/0030-fstools-format-a-UUID-without-assuming-its-alignment.patch` (adds the fstools patch `package/system/fstools/patches/100-libblkid-tiny-format-a-UUID-without-assuming-its-alignment.patch`), for git.openwrt.org/project/fstools, carried by openwrt/openwrt until then.

Problem: libblkid-tiny's `blkid_probe_set_uuid_as()` reads the UUID it is given through an `unsigned short` pointer, but the probes pass pointers into on-disk structures of any alignment: btrfs passes its device item's UUID, at the odd offset 0x10b of the superblock. A misaligned load is undefined behavior, and the function made it even for a name it ignores.

Why it matters here: the `ubsan` profile's fourth run trapped here: `block info` died on the data disk that `wrt-data init` had just formatted, so the data disk was never set up, and every module that uses it failed.

What the patch does: the UUID is formatted a byte at a time, which gives the same text.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### ucode: ubus values read without assuming their alignment

Patch: `patches/openwrt/0031-ucode-ubus-read-blob-values-without-assuming-their-a.patch` (adds the ucode patch `package/utils/ucode/patches/120-ubus-read-blob-values-without-assuming-their-alignment.patch`), for github.com/jow-/ucode, carried by openwrt/openwrt until then.

Problem: the ubus module's `blob_to_ucv()` reads 64-bit integers and doubles through a `uint64_t` pointer, but blob attributes are padded to four bytes, so their data is only four-byte aligned: a misaligned load, which is undefined behavior. It is the fault of patch 0025, in ucode's copy of the conversion.

Why it matters here: the `ubsan` profile's first R6S run trapped here: uhttpd's ucode handler died converting a ubus reply with such a value, and the metrics stopped after the first collector.

What the patch does: every scalar is read with libubox's `blobmsg_get_*()` accessors, whose `blobmsg_get_u64()` reads two aligned 32-bit words.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### qosify: DNS packets received with the IP header aligned

Patch: `patches/openwrt/0032-qosify-dns-receive-packets-with-the-IP-header-aligne.patch` (adds the qosify patch `package/network/config/qosify/patches/101-dns-receive-packets-with-the-IP-header-aligned.patch`), for git.openwrt.org/project/qosify, carried by openwrt/openwrt until then.

Problem: `qosify_dns_socket_cb()` receives each packet at the start of its buffer, so the IP header, after the 14-byte Ethernet header, is two bytes off a four-byte boundary, and qosify reads it through a `struct ip` or `struct ip6_hdr` pointer, whose alignment is four: a misaligned access, which is undefined behavior.

Why it matters here: the `ubsan` profile's second R6S run trapped here once, when a DNS reply reached qosify's DNS socket during a trial boot.

What the patch does: the packets are received two bytes into a four-byte aligned buffer, as the kernel's `NET_IP_ALIGN` does, so the IP header is aligned, with a VLAN tag or without. It is the least change that fixes today's qosify; patch 0034's DNS sockets, which receive each packet from its IP header on, start the aligned buffer with it instead.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### base-files: the firmware keys in /etc/usign/keys

Patch: `patches/openwrt/0033-base-files-fwtool-read-the-firmware-keys-from-etc-us.patch`, for openwrt/openwrt.

Problem: sysupgrade checks an image's signature with ucert against the keys in `/etc/opkg/keys` (`fwtool_check_signature()`). They are usign keys, kept in opkg's directory, which an image built with apk no longer needs for anything else.

Why it matters here: the image has no opkg left, and no `/etc/opkg` (`device-modernization` D5): wrt-keyring puts the release keys in `/etc/usign/keys`, and sysupgrade has to find them there.

What the patch does: `fwtool_check_signature()` reads `/etc/usign/keys`, named after the tool whose keys they are as `/etc/apk/keys` is, and `/etc/opkg/keys` on an image without that directory, so upstream's images check their signatures as before.

Verification log: the firmware/ab-upgrade tests take a signed upgrade and refuse an unsigned one on both boards.

### qosify: tcx links, and DNS names learnt on each device

Patch: `patches/openwrt/0034-qosify-attach-as-tcx-links-and-learn-DNS-names-on-ea.patch` (adds the qosify patches `package/network/config/qosify/patches/102-dns-learn-from-a-packet-socket-on-each-device.patch` and `103-interface-attach-the-classifiers-as-tcx-links.patch`, and passes the `defaults` option `tcx` on in the init script), for git.openwrt.org/project/qosify, carried by openwrt/openwrt until then.

Problem: qosify attaches its classifiers as `cls_bpf` filters under `clsact`, and redirects with tc filters: four u32 filters mirror DNS replies to `ifb-dns`, and a mirred filter sends the ingress to the interface's ifb when it is shaped. All of them stay on the device when qosify is killed. A program attached as a tcx link runs before them whatever either asks for. DNS learning reads the mirrored packets from a raw socket on `ifb-dns` as Ethernet frames, but the packets of a device without a link-layer header, such as pppoe-wan, come without one, so qosify learns no name there.

Why it matters here: einat runs as tcx links on pppoe-wan, so qosify's filters were the only legacy filters on the WAN port, and their order after einat held by the kernel's rule that tcx runs first rather than by anything either asked for (`device-modernization` D4). A rule by DNS name never matched on the PPPoE WAN.

What the patches do:
- 102: DNS learning opens a packet socket on each device qosify sets up: `SOCK_DGRAM`, so that each packet starts with its IP header whatever the link layer, with a classic BPF filter for UDP from port 53 over IPv4 (not a later fragment) or IPv6, and `PACKET_IGNORE_OUTGOING`. It gets a copy of each reply, which goes on untouched. `ifb-dns` and its four filters go, and the socket goes with the device's setup and with the process. DNS over TCP was never learnt (the parser takes UDP alone), and still is not.
- 103: the classifiers attach as tcx links with `BPF_F_AFTER` (`bpf_link_create()` on the loaded program); einat asks to run first (`BPF_F_BEFORE`), so the order holds whichever starts first. The program is named `qosify_classify`, as a tcx link has no name of its own to tell it from einat's. The links go with the process, however it ends, and with the device; patch 0010's start anew on a replaced device attaches anew. The ingress classifier redirects to the interface's ifb itself (`bpf_redirect()`), when the ifb's index is in the `ingress_ifb` map, which qosify writes as it creates the ifb; on a device without a link-layer header, the packet first gets an Ethernet header, which the ifb strips as it returns the packet (an ifb takes link-layer frames, and at ingress `bpf_skb_change_head()` has no MTU limit). A kernel that refuses a tcx link (`EINVAL` or `EOPNOTSUPP`) gets `cls_bpf` under `clsact`, which runs after every tcx program, as does the `defaults` option `tcx` set to 0 on any kernel; qosify adds `clsact` only then.

Verification log: the network/tc-hook-order and network/qos tests on both boards: einat's tcx programs first and qosify's after them, with no legacy filter and no ifb; a `dns:` rule classifying a flow on pppoe-wan; ingress shaping through the ifb; and the `clsact` fallback with `tcx` set to 0. 2026-10-11, with every CPU of the VM kept busy, eight rounds of restarts of qosify and einat and redials on the R6S left einat's programs and then qosify's on pppoe-wan's tcx hooks every time, 26 to 36 s after the restarts and 27 to 42 s after the hang-ups.

### procd: init scripts triggered on unmounts too

Patch: `patches/openwrt/0035-procd-trigger-init-scripts-on-unmounts-too.patch`, for openwrt/openwrt.

Problem: `procd.sh` gives init scripts mount triggers for `mount.add` only, so a service whose disk is unmounted keeps serving from the mount point until someone restarts it. The helper also turned the mount points of several paths into one condition, an `eq` against all of them joined by newlines, which never matched; and `_procd_add_mount_trigger` named the script to run from whatever `$name` its caller had.

Why it matters here: ksmbd's shares are on the data disk, and services/file-sharing requires that no share be offered once the disk is gone (`device-robustness` D1, D3).

What the patch does: one helper registers a trigger for an event and an action on the mount points that hold the given paths. `_procd_add_action_mount_trigger` is it with `mount.add`, as before, and the new `_procd_add_action_unmount_trigger`, with `procd_add_restart_unmount_trigger` and `procd_add_reload_unmount_trigger`, with `mount.remove`. The mount points become separate arguments, so several of them give one `or`, and `_procd_add_mount_trigger` names the script from `$initscript`. A single mount point's trigger is the same as before.

Verification log: 2026-10-12, the triggers `procd.sh` builds, compared before and after with the build tree's host `jshn`: the same for one mount point with restart, reload and start (as ubox's log, ksmbd-tools, transmission, nfs-kernel-server and postgresql call them), one `or` for two mount points, and `mount.remove` from the unmount helpers.

### fstools: the mount point of a removed device's unmount

Patch: `patches/openwrt/0036-fstools-report-the-mount-point-of-a-removed-device-s.patch` (adds the fstools patch `package/system/fstools/patches/101-block-report-the-mount-point-of-a-removed-device-s-unmount.patch`), for fstools, carried by openwrt/openwrt until then.

Problem: when a hotplugged device is removed, `block` has blockd forget the device (`hotplug` with `remove`) before it unmounts it. blockd's `umount` handler then no longer finds the device, and sends `mount.remove` with the mount point it kept in a static buffer from an earlier unmount, or with none.

Why it matters here: the data disk is a hotplug mount at `/mnt/data`, and ksmbd's unmount trigger (patch 0035) waits for a `mount.remove` that names it (`device-robustness` D2).

What the patch does: `block` unmounts a removed device first and has blockd forget it after, and blockd reports the mount point of the device being unmounted, or none for a device it does not know, instead of one kept across calls.

Verification log: on both boards, `echo remove` to the data disk's `uevent` gives a `mount.remove` that names `/mnt/data` (the file-sharing test "Data disk removed while sharing").

### qosify: a long device's ifb named after its own name

Patch: `patches/openwrt/0037-qosify-name-a-long-device-s-ifb-after-its-own-name.patch` (adds the qosify patch `package/network/config/qosify/patches/104-interface-name-a-long-device-s-ifb-after-its-own-name.patch`, and changes `qosify-status`), for git.openwrt.org/project/qosify, carried by openwrt/openwrt until then.

Problem: for a device name of 12 to 15 characters, `interface_ifb_name()` keeps the first two characters and takes the rest at `len - (IFNAMSIZ + 6) - 1`, 8 to 11 characters before the name: undefined behavior, and an ifb named after whatever precedes the name in memory. `qosify-status` derives the ifb's name as `printf %.16s "ifb-$ifname"`, which disagrees with the daemon's for those lengths.

Why it matters here: ingress shaping redirects to the interface's ifb (patch 0034), and a VLAN or a tunnel can have a long name (`device-robustness` D5).

What the patch does: the tail starts at `len - (IFNAMSIZ - 7)`, the last nine characters, which make fifteen with `ifb-` and the first two. `ubus call qosify status` reports each active interface's ifb as `ifb`, and `qosify-status` shows that device. `PKG_RELEASE` goes to 6.

Verification log: the network/qos test "Ingress shaping on a device with a long name" on both boards.

### wsdd2: the random seed without overflow

Patch: `patches/packages/0005-wsdd2-seed-without-overflow.patch` (adds the package patch `020-wsd-seed-without-overflow.patch`), for openwrt/packages: wsdd2's own repository, github.com/Netgear/wsdd2, is gone, and openwrt/packages builds it from its mirror.

Problem: `set_seed()` folds the endpoint's UUID into its seed by shifting the first 16 bits of each pair left by 16 as an `int`. For a value of 0x8000 or more, as half of all UUIDs have, the result does not fit in an `int`, which is undefined behavior. It also has `time()` write a `time_t` into an `unsigned long`, which is too small for it on a 32-bit target with a 64-bit `time_t`, as musl's are.

Why it matters here: the `ubsan` profile's fifth run trapped here: wsdd2 trapped on almost every start, and procd started it again, through every suite.

What the patch does: the shift is done as `unsigned long`, and the seed takes `time()`'s result. `srand48()` takes the low 32 bits of its seed, which stay the same.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### podman: equal database paths matched without resolving them

Patch: `patches/packages/0006-podman-match-equal-database-paths-without-resolving-.patch` (adds the podman patch `utils/podman/patches/020-libpod-match-equal-database-paths-without-resolving-them.patch`), for podman, carried by openwrt/packages until then.

Problem: `ValidateDBConfig` compares the paths the database recorded with the runtime's own, resolving the symlinks of each in turn; a path is resolved only if it exists. Without `--runroot`, the runtime's run root is the database's, the same string. The storage creates the run root after the validation, so a second podman process that creates it between the first one's two resolutions makes the same path compare unequal: `database run root "/run/containers/storage" does not match our run root "/tmp/run/containers/storage": database configuration mismatch`. The SQLite and the BoltDB state share the logic. Upstream fixed the same race for the volume path by creating it first (containers/podman#23515).

Why it matters here: the image's run root goes through `/run` → `/var/run` → `/tmp/run`, and wrt-containers and wrt-sync run podman at the same time after a boot or a mount of the data disk. CI run 37324813891 lost a device sync to it (`device-robustness` D4).

What the patch does: both states resolve the paths only when they differ as strings; equal paths match. `PKG_RELEASE` goes to 4.

Verification log: the services/containers test "Runtime commands at the same time" runs ten rounds of eight `podman info` at once, each on a scratch storage whose run root does not exist yet. Concurrency alone reproduced nothing in ten rounds without the patch, even with the run root behind 32 symlinks: the window is two path resolutions wide. A symlink on the run root's path that keeps changing its target between two names of one directory (a bind mount), as a concurrent creation changes how the path resolves, made all ten rounds fail without the patch (2026-10-12, R6S).

### podman: the storage's feature probes leave no mounts behind

Patch: `patches/packages/0007-podman-lock-the-storage-s-home-mount-for-its-lazy-fe.patch` (adds the podman patch `utils/podman/patches/021-overlay-lock-home-s-mount-for-the-lazy-feature-probes.patch`, to its vendored copy of go.podman.io/storage), for go.podman.io/storage, carried by openwrt/packages until then.

Problem: the storage's overlay driver probes three kernel features when it is first asked about them, after its initialization: idmapped lower layers, in `Status()`, which `podman info` calls, and in the creation of a layer or a container; volatile mounts, in `Status()` and when it mounts a layer; and data-only lower layers. Each probe mounts in a new directory under the driver's home, then unmounts by path. The store holds its graph lock while the driver initializes, which binds the home onto itself unless it is a mount point already (`mount.MakePrivate`), and while `Cleanup()` unmounts the home at a command's end. It does not hold it for `Status()` or the creations. When another process binds the home while a probe has its mounts under the home's previous mount, the bind hides them. podman warns `Unmount ".../overlay/compat1721885628/lower-mapped": invalid argument`, the probe's directory cannot be removed, and the mounts stay until a reboot.

Why it matters here: the storage is on the data disk, and wrt-containers and wrt-sync run podman at the same time after a boot or a mount of the data disk, on a run root in RAM that has no record of the probes yet. Mounts left under the storage keep the data disk's mount busy until a reboot. CI run 38556156281 lost the services/containers test "Runtime commands at the same time" to it in both attempts: its cleanup could not remove the scratch storage (`Resource busy`).

What the patch does: the driver gets a lock of its own, `home.lock` in the `overlay` directory of the run root. It is held while the driver binds the home, while `Cleanup()` unmounts it, and while a probe that runs after the initialization mounts under the home. It keeps two operations on one mount apart, as the graph lock does for the probes of the initialization, and a probe runs once per run root, so once per boot. Taking the graph lock in `Status()` instead would leave the creations' probes unlocked: they run under the layer store's lock, after which the graph lock cannot be taken. `PKG_RELEASE` goes to 5.

Verification log: the services/containers test "Runtime commands at the same time" runs ten rounds of eight podman commands at once, three in a row each, with the probes' records removed as they appear, so that every command probes. Without the patch, 7 and 8 of the 10 rounds left the probes' mounts behind in two runs; with it, none of 30 rounds in three runs did, and every command succeeded (2026-10-15, R4S).

### luci-base: the host tools built in the host build directory

Patch: `patches/luci/0001-luci-base-build-po2lmo-and-jsmin-in-the-host-build-d.patch`, for openwrt/luci.

Problem: luci-base's host build compiles `po2lmo` and `jsmin` with `make -C src/`, in the package's own source directory, after it has written its prepared stamp. Their objects and binaries are then newer than that stamp, so every build prepares luci-base again, for the host and for the target, and packages it anew.

Why it matters here: with the rest of build-acceleration, luci-base was the only package a build with nothing changed still prepared and compiled.

What the patch does: `Host/Prepare` already copies `src/` into the host build directory, so `Host/Compile` builds there, and `Host/Install` takes the tools from there.

Verification log: 2026-10-04, both tools build from a copy of `src/`, as in the host build directory, and with the patch a build with nothing changed no longer prepares luci-base.

### luci-base: the string hash without shifting a negative value

Patch: `patches/luci/0002-luci-base-hash-without-shifting-a-negative-value.patch`, for openwrt/luci.

Problem: `sfh_hash()`, which keys LuCI's translation catalogs, shifts the third of the trailing bytes, as a `signed char`, left by 18 bits. For a byte of 0x80 or more, as UTF-8 text has, that shifts a negative value, which is undefined behavior.

Why it matters here: the `ubsan` profile's third run trapped here translating a page into Simplified Chinese, and the page did not render.

What the patch does: the value is shifted as `uint32_t`. That keeps every hash as GCC computed it, so the catalogs that `po2lmo` made still match.

Verification log: see the `ubsan` run in `docs/undefined-behavior.md`.

### toolchain: rebuilt with its targets when its inputs change

Patch: `patches/openwrt/0038-toolchain-rebuild-it-and-its-targets-when-its-inputs.patch`, for openwrt/openwrt, on top of patch 0009.

Problem: the toolchain components name their prepared stamps without their content, so a component is built again only once its build directory is gone. Only buildbot mode cleans up: it removes the toolchain when the last git commit of `toolchain/` changes, and `check-toolchain-clean.sh` runs `make targetclean` when the GCC version or `toolchain/build_version` does. Outside buildbot mode, a changed toolchain patch leaves the old toolchain in place, and so does an uncommitted one, or one in a tree without `.git`. No mode covers the generic kernel patches, from which the toolchain's kernel headers come. The cleanup also reaches only the configuration at hand: other target directories built with the same toolchain keep objects of the old one.

Why it matters here: patch 0020 added a GCC patch, and `just toolchain-build dev` in an existing tree did not rebuild GCC. Every board builds in directories of its own on the one board-neutral toolchain (board-model D2), so cleaning the configuration at hand would leave the other board's packages compiled by the old toolchain (`build-integrity` D1, D2).

What the patch does:
- `.ver_check` holds the content hash (`find_md5_reproducible`) of `toolchain/` and of the generic kernel files of the configured kernel version: its version file, the backport, pending and hack directories, and the files directories, as `include/target.mk` picks them. A toolchain of other content is removed with its build directory, to be built anew as a whole: its three GCC passes share one source tree, so rebuilding a component alone would leave the toolchain partly old.
- Each target build directory records the toolchain it was built with, by directory name and content (`$(BUILD_DIR)/.toolchain`). When that is not the toolchain at hand, the build and staging directories are removed, so a change of the GCC version or the C library, which builds a toolchain in another directory, cleans the target too.
- Both checks run where buildbot mode's ran: every make that reads the top-level Makefile remakes the `info.mk` it includes before building anything, so the first make of a build decides, before world starts any other. They run in every mode, with or without git, and an uncommitted edit counts.
- `toolchain/build_version` is a file of `toolchain/`, so bumping it still rebuilds. `check-toolchain-clean.sh`, `toolchain_rebuild_check` and `.toolchain_build_ver` go.

The first make after the patch rebuilds the toolchain and each target once, as none has the new records yet.

Verification log: `tests/build/test_boards.py` runs the patched check on a stand-in tree: "Keep each board's build with its toolchain" for the target records, "Keep the toolchain in buildbot mode" and "Check the version from parallel makes" for the toolchain's.

2026-10-12, on the VM with the dev profile: the first `just build r4s dev` after the patch found a toolchain whose record named a git commit, built it anew as a whole, Rust's host toolchain with it, and built the R4S anew. A second `just build r4s dev` compiled nothing: its time report held only the kernel's two forced passes (41 s), and ccache saw no cacheable call. `just build r6s dev` then kept the toolchain and built the R6S anew, as its build directory had no record yet.

2026-10-13, on the VM: with a scratch GCC patch that changes nothing built (a new file in GCC's source), `just build r4s dev` built the toolchain anew and compiled all 475 stages of the R4S, at 14.8 % ccache hits, as the new compiler differs; `just build r6s dev` kept that toolchain and compiled all 481 stages of the R6S. With the patch removed, the R4S's build built the toolchain anew again, and both boards compiled every stage anew, at 99.99 % hits: the toolchain built without the patch is the one built before it, whose entries ccache kept. CI's run 38305783785 built the toolchain in the ci profile, which is buildbot mode, and neither board's build compiled any part of it.
