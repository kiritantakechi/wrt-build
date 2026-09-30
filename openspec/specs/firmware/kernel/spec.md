# firmware/kernel Specification

## Purpose
Define the firmware kernel's version, the kernel features that the eBPF datapath, containers, and storage require, and the default TCP congestion control algorithm.

## Requirements

### Requirement: Kernel version follows upstream
The kernel version SHALL equal the version that the rockchip target selects by default in the pinned upstream commit, currently the 6.18.y series.

#### Scenario: Check running kernel
- **WHEN** the running kernel version is inspected on the router
- **THEN** the version matches the kernel version that the rockchip target selects in the upstream commit pinned for this build

### Requirement: Provide BTF
The kernel MUST provide its own BTF type information (`/sys/kernel/btf/vmlinux`), and BTF for each loaded kernel module.

#### Scenario: Check BTF
- **WHEN** `/sys/kernel/btf/` is inspected after boot
- **THEN** `vmlinux` exists and is not empty, and loaded modules have their corresponding BTF files

### Requirement: BPF and cgroup v2
The kernel SHALL enable the BPF syscall, the BPF JIT, BPF events, cgroups with BPF attach support, and tcx. The system SHALL mount only the unified cgroup v2 hierarchy, and MUST NOT enable the v1 memory controller.

#### Scenario: Check cgroup mounts
- **WHEN** the cgroup mounts are inspected after boot
- **THEN** `/sys/fs/cgroup` is cgroup2, and no v1 controller is mounted

#### Scenario: Load a tcx program
- **WHEN** a BPF program is attached at the tcx ingress of a network port
- **THEN** the attach succeeds and `bpftool net show` lists it

### Requirement: Root and overlay filesystems built in
The kernel SHALL build in EROFS (including lz4 decompression) and F2FS with compression (including zstd), without depending on any loadable module.

#### Scenario: Boot without loading modules
- **WHEN** the router boots
- **THEN** the root filesystem mounts as erofs and the overlay mounts as f2fs with compression, and no filesystem module is loaded along the way

### Requirement: Same kernel boots in the emulator
The kernel SHALL build in the drivers the QEMU `virt` platform needs: PL011 serial, the generic PCIe host controller, an SD host controller on PCI (sdhci-pci) for the SD card, virtio network devices, and the i6300esb watchdog. The shipped kernel then boots in the emulator without modification and uses the SD card, network, and watchdog. These drivers MUST be built into the kernel, not as modules.

#### Scenario: Shipped kernel boots in the emulator
- **WHEN** the emulator's U-Boot boots the kernel of the shipped factory image
- **THEN** the serial console produces output, the root filesystem on the SD card is mounted, and both virtio NICs and the watchdog device are detected

### Requirement: Drivers for the R4S ports
The kernel SHALL register the drivers of both R4S network ports at boot with no manual step: the RK3399 GMAC driver (dwmac-rk) for the WAN port and the RTL8111 driver (r8169) for the LAN port. The emulator has neither device, so the drivers are checked while they wait for their devices.

#### Scenario: Port drivers registered
- **WHEN** the drivers registered with the kernel are listed after boot
- **THEN** the platform bus lists the RK3399 GMAC driver and the PCI bus lists the r8169 driver

### Requirement: BBRv3 as default congestion control
The system's default TCP congestion control SHALL be BBRv3, and the default queueing discipline SHALL be fq.

#### Scenario: Check congestion control settings
- **WHEN** `net.ipv4.tcp_congestion_control` and `net.core.default_qdisc` are read after boot
- **THEN** they are `bbr` and `fq` respectively, and `/proc/kallsyms` contains the BBRv3-only callbacks `bbr_skb_marked_lost` and `bbr_tso_segs` from the `tcp_bbr` module (OpenWrt enables `MODULE_STRIPPED`, which removes `MODULE_VERSION`, so the module version is not visible)

#### Scenario: Router-originated connections use BBR
- **WHEN** the router itself opens a TCP connection
- **THEN** `ss -ti` shows bbr as the congestion control for that connection

### Requirement: BBRv3 is the only kernel source change
The only patches that modify kernel source SHALL be the BBRv3 set, and they MUST NOT include NAT, fullcone, shortcut-fe, or other forwarding acceleration patches.

#### Scenario: Audit kernel patches
- **WHEN** all patches in the patch queue that modify kernel source are listed
- **THEN** only the BBRv3 series is among them

### Requirement: Standard vermagic
The kernel module version identifier (vermagic) SHALL be computed the standard upstream OpenWrt way, and MUST NOT be replaced with a fixed value unrelated to the kernel configuration.

#### Scenario: Install a kmod from the same build
- **WHEN** any kmod from the same build as the image is installed on the router
- **THEN** the installation succeeds and the module loads normally

#### Scenario: Reject a kmod with a different kernel config
- **WHEN** installing a kmod produced by a build with a different kernel configuration is attempted
- **THEN** the package manager refuses to install it because the kernel dependency is not satisfied
