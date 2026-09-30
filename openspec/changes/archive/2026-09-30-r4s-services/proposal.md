# Proposal

## Why

Besides routing, the R4S also serves as a NAS, a download box, a container host, and a remote-networking endpoint. The SD card is the only boot medium, so write-heavy workloads must move off it.

Apps such as qBittorrent need Qt6 and libtorrent, and packaging them natively would bloat the own feed considerably. These apps therefore run in containers, and the firmware keeps only the core components.

## What Changes

- **USB SSD data disk**
  - Filesystem: btrfs, with mount options `compress=zstd:3,noatime`.
  - Subvolume layout: `@containers`, `@downloads`, `@shares`, `@logs`, plus `.snapshots`.
  - Mounted by UUID through fstools block-mount.
- **Services wait for the disk**: services that depend on the data disk use procd's mount trigger (`procd_add_restart_mount_trigger`) to start or restart once the disk is mounted, instead of polling with sleep.
- **Containers**
  - podman + crun + netavark; container storage (graphroot) lives on `@containers`.
  - netavark only creates the bridge and assigns addresses, and installs no firewall rules (`firewall_driver = "none"`). The container bridge belongs to a dedicated fw4 zone; outbound address translation is done by einat, as for the LAN; ports exposed externally use fw4 port forwards.
  - The container bridge podman0 joins dae's LAN binding.
  - Apps such as qBittorrent all run as containers.
- **File sharing**
  - ksmbd (the in-kernel SMB server) plus ksmbd-tools.
  - Exposed on the LAN only; shares live on `@shares`.
- **Remote networking**
  - WireGuard (in-kernel) and Tailscale.
  - tailscale0 joins dae's LAN binding.
- **Monitoring**: prometheus-node-exporter-ucode, exposed on the LAN only.
- **Logs**: persistent logs go to `@logs`, so the SD card sees almost no writes.
- **Degraded mode without the data disk**: containers and SMB do not start; core routing is unaffected.

## Capabilities

### New Capabilities

- `storage/data-disk`: the USB SSD's filesystem, subvolume layout, mounting, startup ordering of mount-dependent services, persistent logs, and degraded behavior when the data disk is missing.
- `services/containers`: the podman runtime, storage location, how container networking relates to the proxy, and the boundary for running apps as containers.
- `services/file-sharing`: ksmbd share exposure and share directories.
- `services/vpn`: WireGuard and Tailscale, and how they relate to the transparent proxy.
- `services/monitoring`: metrics export and exposure.

### Modified Capabilities

(None.)

## Impact

- **kmod**: kmod-fs-btrfs, kmod-usb-storage-uas, kmod-fs-ksmbd, kmod-wireguard, kmod-tun (for Tailscale), kmod-veth.
- **Packages**: btrfs-progs, block-mount, podman, crun, netavark, ksmbd-tools, tailscale, prometheus-node-exporter-ucode.
- **Depends on other changes**:
  - `r4s-build-foundation`: cgroup v2 and kernel features.
  - `r4s-ebpf-datapath`: binding podman0 and tailscale0 to dae.
- **Kernel**: add `USB_PCI` and `USB_XHCI_PCI` to the virt driver group in `config/kernel.config` so the emulator can attach a USB data disk.
- **Verification**: in the emulator, a `usb-uas` device stands in for the SSD, and plugging and unplugging go through QEMU's control interface; the sandbox gains a container registry, headscale, a WireGuard peer, and a tailnet peer. Every scenario in the five specs is an automated test in `just test`; since the emulator has no temperature sensor, the temperature scenario checks the RK3399 sensor driver and the hwmon collector.
- **Hardware risk**: the R4S's USB3 port has limited power, and some USB-to-SATA/NVMe bridge chips are unstable in UAS mode. The hardware must be selected carefully; no step measures it before release, and the router keeps working without the data disk.
- **Security**: ksmbd has a history of serious vulnerabilities. This relies on picking up kernel fixes weekly and exposing the service only on the LAN.
