# Design

## Context

For the motivation, see proposal.md. Everything below was checked against the upstream sources (OpenWrt main `1019293`, packages `a637759`):

- **podman**:
  - Version 5.8.4. `containers.conf` defaults to `network_backend = "netavark"`, `firewall_driver = "nftables"`, and `cgroup_manager = "cgroupfs"`.
  - The `storage.conf` driver is changed to `overlay` with sed (`utils/podman/Makefile:113`).
  - `podman.init` only runs `podman system service`; it does not start containers at boot.
- **netavark**: version 1.17.2; the default firewall backend is nftables, which depends on `kmod-nft-nat`.
- **Persistent logs**: upstream `log.init` already supports placing `log_file` on a mount point. If the mount point is not yet mounted at boot, it skips it, and it rotates by size with `-S` (`package/system/ubox/files/log.init:53-66`).
- **node-exporter**: `prometheus-node-exporter-ucode` defaults to `listen_interface 'loopback'`, port 9101.
- **tailscale**: the init script defaults to `fw_mode nftables` (`net/tailscale/files/tailscale.init:22-31`).
- **ksmbd**: ksmbd-tools 3.5.7; the kernel module is `kmod-fs-ksmbd` (`package/kernel/linux/modules/fs.mk:346`), and LuCI has a matching luci-app-ksmbd.
- **procd**: provides `procd_add_restart_mount_trigger` (`procd.sh:431`).
- **Upstream change**: the datapath's einat, fw4 rules, and dae binding come from `r4s-ebpf-datapath`; the mark allocation table is also established there.
- **Kernel**: the rockchip config does not enable `USB_PCI` or `USB_XHCI_PCI` (checked against the 6.18.52 build output), and the emulator's USB controller needs both.
- **Verification environment**: the foundation's emulation environment, plus the ISP, internet, and proxy nodes that datapath adds (datapath D11).

## Goals / Non-Goals

**Goals:**
- The SD card sees only system writes and a small amount of config writes; all write-heavy workloads run on the USB SSD.
- Firewall and NAT each have a single source: fw4 manages all firewalling, and einat does all NAT (falling back to masquerade when einat is unavailable). The container runtime installs no rules of its own.
- App containers are defined by declaration files and can be applied repeatedly with consistent results.

**Non-Goals:**
- Accessing SMB or other router-local services over VPN.
- Packaging apps such as qBittorrent or AdGuardHome natively in the firmware.
- RAID or multi-disk arrays for the data disk, or off-site backup.
- Time Machine (ksmbd has been chosen over samba4).

## Decisions

### D1. Mount layout

```
USB SSD  (btrfs, label wrtdata, identified by UUID)
  subvolid=5   -> /mnt/data/.pool        (management only; snapshots created here)
  @containers  -> /mnt/data/containers
  @downloads   -> /mnt/data/downloads
  @shares      -> /mnt/data/shares
  @logs        -> /mnt/data/logs
  .snapshots   (under the pool root)
options: compress=zstd:3,noatime,space_cache=v2
```

- **Mounting**: fstools block-mount, with one mount entry per subvolume in UCI fstab: the same UUID, but a different `subvol=`.
- **Initialization**: `wrt-data init` creates the subvolumes and writes fstab. The target disk must be confirmed manually before it runs, because it wipes the entire disk.
- **Alternatives**:
  - Mount the whole disk at a single point and separate data by subdirectory. Rejected: that makes it impossible to snapshot a single subvolume or to wait on a single subvolume with a mount trigger.
  - ext4 or xfs. btrfs was already chosen during exploration.

### D2. Startup ordering for mount-dependent services

- **Approach**: every service that depends on the data disk declares `procd_add_restart_mount_trigger <mount point>` in its init script, and at startup returns immediately without creating directories if the mount point is absent. These services include podman, `wrt-containers`, ksmbd, and persistent logs.
- **Why no directories are created at startup**: this avoids creating directories on the SD card when the data disk is absent, which satisfies the spec's "must not write data to the SD card" rule.
- **Persistent logs specifically**: use the upstream mechanism directly by setting `system.@system[0].log_file=/mnt/data/logs/messages` and `log_size`; no custom service is needed.

### D3. Containers: netavark stays out of the firewall, fw4 manages it all

- **podman configuration**:
  - Set `firewall_driver = "none"` in `containers.conf`; netavark only creates the bridge and assigns addresses, and installs no nft rules.
  - In `storage.conf`, set `graphroot=/mnt/data/containers/storage` and `runroot=/run/containers/storage`.
- **fw4 configuration**: add a `podman` zone that contains podman0:
  - podman → wan: forwarding allowed;
  - lan → podman: forwarding allowed, so the LAN can reach container addresses directly;
  - podman → lan: rejected by default.
- **Outbound address translation**: done by einat, as for the LAN, falling back to masquerade when einat is unavailable. During implementation, confirm that einat's internal network setting includes the container subnet (task 4.2).
- **Exposing ports externally**: implemented with fw4 redirects (DNAT); the external port must not fall within einat's port range 20000-29999.
- **Rationale**:
  - fw4 is the only source of rules, so `nft list ruleset` shows everything at a glance;
  - it avoids stacking netavark's masquerade on top of einat, which would rewrite the external port twice;
  - netavark uses no marks, so there is one less component to register in the allocation table.
- **Cost**: `podman run -p` no longer works; exposing a port requires a fw4 rule.
- **Alternative**: keep netavark's nftables backend. Rejected for the reasons above.

### D4. App containers defined by declaration files

- **Declaration files**: Kubernetes Pod YAML read by `podman kube play`, stored in `/mnt/data/containers/pods/*.yaml`. The source of truth lives in the private config repository and is written by the config push tool.
- **Startup service**: the own feed adds a `wrt-containers` service with a mount trigger on `/mnt/data/containers`. On each trigger, it compares each declaration file's hash with the hash recorded at the last successful apply:
  - if the hash changed, it runs `podman kube play --replace`;
  - if the hash is unchanged, it only ensures that the Pod is running.
  - This satisfies "no rebuild when the declaration is unchanged".
- **Alternatives**:
  - podman-compose. It is not in the upstream feed and would pull in Python. Rejected.
  - One procd service per container. Rejected: too scattered.

### D5. Snapshots

- **Tool**: the own feed adds `wrt-snap`:
  - `wrt-snap now` takes one read-only snapshot each of `@containers` and `@shares` into `.snapshots/<subvolume>/<timestamp>`;
  - `wrt-snap prune` keeps only the last 7 days;
  - cron runs `now` and `prune` once a day.
- **Why `@downloads` and `@logs` are excluded**: downloads can be fetched again and logs rotate on their own, so snapshotting them only wastes space.

### D6. ksmbd

- **Protocol and authentication**: UCI configures ksmbd to bind only to `lan`, with SMB3 as the minimum protocol and no anonymous access.
- **Shares**: all shares point to `/mnt/data/shares/*`.
- **Credentials**: user credentials are written by the config push tool running `ksmbd.adduser` on the device; they are not preset in the image.
- **Firewall**: input on the fw4 wan, wireguard, and tailscale zones is rejected by default, and port 445 is allowed only from lan.

### D7. VPN

- **WireGuard**:
  - Uses `kmod-wireguard`, `wireguard-tools`, and `luci-proto-wireguard`; the interface wg0 sits in its own `wg` zone, with forwarding allowed to lan and wan.
  - wg0 is not added to dae's binding list, so traffic entering over WireGuard goes direct.
- **Tailscale**:
  - Uses the upstream package with `fw_mode nftables`, advertises the LAN subnet route, and can also act as an exit node.
  - The datapath hotplug adds tailscale0 to dae's binding automatically.
  - The marks it uses (`0x40000` and `0x80000` within the mask `0xff0000`) must be confirmed against the tailscale source during implementation and then registered in `config/marks.tsv`.
- **Credentials**: the WireGuard private key and the Tailscale auth key are both written by the config push tool.

### D8. Monitoring

- **Configuration**: `prometheus-node-exporter-ucode` with `listen_interface 'lan'`; port 9101 is open only to the lan zone.
- **Collectors**: cpu, meminfo, netdev, filesystem, and hwmon (temperature). On the R4S, `rockchip-thermal` registers the SoC's thermal zones with hwmon; the emulator has no sensor, so the test checks the driver and the collector instead of a reading.

### D9. New packages and kernel modules

```
kmod-usb-storage kmod-usb-storage-uas kmod-fs-btrfs btrfs-progs block-mount
podman crun netavark conmon
kmod-fs-ksmbd ksmbd-tools luci-app-ksmbd
kmod-wireguard wireguard-tools luci-proto-wireguard tailscale
prometheus-node-exporter-ucode (+ collectors)
wrt-containers wrt-snap wrt-data   (own feed)
```

All of these go into `config/services.seed`.

### D10. Verification: the USB data disk and all peers run in the emulator

```
qemu ... -device qemu-xhci,id=xhci
  data disk : -drive if=none,id=ssd,file=ssd.qcow2 -device usb-uas,id=uas,bus=xhci.0,port=1
              -device scsi-hd,bus=uas.0,drive=ssd
  QMP       : device_add / device_del  -> late attach, other port (port=2), foreign btrfs disk
sandbox additions:
  inet     : registry (distribution, TLS by test CA)   headscale (+ embedded DERP, same CA)
  wg-peer  : wireguard-go + wireguard-tools             remote WireGuard device
  ts-peer  : tailscaled --tun, logged into headscale    tailnet device
  client-a : smbclient, curl
test image: busybox + musl taken from the shipped rootfs -> OCI image -> skopeo push
```

- **Kernel additions**: add `USB_PCI` and `USB_XHCI_PCI` to the virt driver group in `config/kernel.config`. The UAS driver comes from `kmod-usb-storage-uas` in the image, and the emulator uses a `usb-uas` device, so it exercises the same driver as the device.
- **Plugging and unplugging**: done through QMP `device_add` and `device_del`, so "mount 30 seconds late", "move to another USB port", "insert another disk", and "unplug the disk to degrade" all run automatically.
- **Test container image**: an OCI image assembled directly from busybox and musl in the shipped rootfs, so the architecture always matches and no internet access is needed. The app container in the tests is a busybox httpd that stands in for qBittorrent.
- **Test CA**: the registry and headscale share one test CA. The fixture writes the CA certificate into the router's `/etc/ssl/certs/`; it exists only in the test overlay and never enters the image.
- **Credentials**: the SMB user, WireGuard keys, and Tailscale auth key are all written by the fixture the same way the config push tool writes them, which also verifies "no credentials preset in the image".
- **Tests map one-to-one to specs**: `tests/storage/test_data_disk.py`, plus `test_containers`, `test_file_sharing`, `test_vpn`, and `test_monitoring` under `tests/services/`.
- **Snapshot expiry**: the test advances the system clock one day at a time and runs the cron job once per day, with no real-time waiting.
- **What only real hardware shows** (no step needs the device):
  1. A temperature reading: the test checks that `rockchip-thermal` is registered and that the hwmon collector succeeds (D8).
  2. The stability of an SSD and enclosure in UAS mode under load, and USB power: not verified; they depend on the hardware chosen, not on the firmware (see Risks).
  3. macOS Finder: `smbclient` speaks SMB 3 to ksmbd the way Finder does, so the file-sharing scenarios cover the protocol; copy throughput is not measured.

## Risks / Trade-offs

- **[Insufficient USB3 power, or bridge chips unstable in UAS mode]** → Prefer low-power SATA SSDs and stable bridge chips such as ASM1153 and JMS578. If problems occur, add the device to the `usb-storage` quirks to fall back to BOT mode; `docs/services.md` says how.
- **[The emulator only covers behavior above the driver]** Bridge chip, power, and USB link reset issues do not appear in the emulator, and nothing tests them before release. → The data disk is optional to the router's function: without it, routing and the other services keep working (data-disk spec, "Degraded mode without the data disk"), so a flaky enclosure degrades storage only.
- **[`podman run -p` stops working with `firewall_driver = "none"`]** This is a deliberate trade-off; all port exposure goes through fw4 redirects, and this is documented.
- **[einat's internal network setting does not include the container subnet]** → `test_containers.py` uses `netprobe` to check the mapping behavior of container traffic.
- **[btrfs problems after an unexpected power loss]** btrfs is copy-on-write and usually stays consistent; regular read-only snapshots serve as recovery points.
- **[ksmbd's vulnerability history]** → Exposed on the LAN only; the kernel is updated with the weekly bump.
- **[Container images must be pulled from the internet]** The container subnet is already in dae, so image pulls can go through the proxy according to the rules.

## Migration Plan

1. Deploy firmware that includes this change.
2. Attach a new SSD, run `wrt-data init`, and confirm the target disk when prompted.
3. Use the config push tool to write the SMB user, WireGuard private key, Tailscale auth key, and Pod declaration files.
4. Rollback: unplug the data disk, and the system degrades to routing only; to roll back the firmware, switch back to the previous slot with A/B.

## Open Questions

- The specific SSD and enclosure will be chosen after hands-on testing; this does not affect the specs.
- The log rotation size limit is set to 64 MiB for now and can be adjusted at any time.
