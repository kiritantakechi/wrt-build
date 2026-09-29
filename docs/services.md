# Services

The router's services beyond routing (r4s-services): a USB SSD as the data disk, app containers, SMB file sharing, WireGuard and Tailscale, and metrics for Prometheus. Everything that writes a lot lives on the data disk; the SD card holds the system only. Without the data disk the router routes, filters, translates, proxies and resolves as before, and the services that keep their data there wait for it.

## The data disk

One USB SSD, btrfs, identified by its filesystem UUID (any port, any device name). Its top level is mounted at `/mnt/data` with `compress=zstd:3,noatime,space_cache=v2`, and its subvolumes sit at fixed paths in it:

| Path | Holds |
|---|---|
| `/mnt/data/containers` | podman's storage, the Pod declarations (`pods/`) and their data |
| `/mnt/data/downloads` | downloads (the app containers') |
| `/mnt/data/shares` | the SMB share |
| `/mnt/data/logs` | the persistent system log, `messages`, rotated at 64 MiB |
| `/mnt/data/.snapshots` | read-only snapshots, `<subvolume>/<UTC time>` |

### Set one up

`wrt-data init` erases a disk and makes it the data disk. Without an argument it lists the USB disks; with one, it asks for the device's full name again before it erases anything:

```sh
wrt-data init             # USB disks: device, size, model
wrt-data init /dev/sda    # then type /dev/sda to confirm
wrt-data status           # the mount and the subvolumes
```

It creates the filesystem (label `wrtdata`) and the subvolumes, names the disk by UUID in the fstab entry `wrtdata`, and mounts it. The image holds that entry from its first boot, disabled and without a disk, so that the services below know from the start where their data will be. An existing data disk on a new or reset router is not initialized again: set its UUID (from `block info`) in that entry instead, with `uci set fstab.wrtdata.uuid=<UUID>`, `uci set fstab.wrtdata.enabled=1` and `uci commit fstab`, then reboot.

### What waits for it

The container service, SMB and the persistent log start only while `/mnt/data` is mounted, and start again each time it is. Until then they run nothing and write nothing: `/mnt/data` on the SD card stays an empty directory. A disk plugged in after boot brings them up without a reboot. Take it out with the router off: pulled out while in use, the filesystem stays behind, detached, for as long as a file on it is open, and the disk comes back cleanly only after a reboot.

### Snapshots

At 03:17 every day cron takes a read-only snapshot of `containers` and `shares` (`wrt-snap now`) and deletes those older than the last seven days, today's included (`wrt-snap prune`). Take one yourself at any time:

```sh
wrt-snap now              # prints the two new snapshots
wrt-snap list shares      # the snapshots of shares, oldest first
```

### Restore a file from a snapshot

A snapshot is a read-only copy of the subvolume as it was: copy the file back out of it. Set `file` to the file's path in the share; the commands take it from the newest snapshot (any other from `wrt-snap list shares` works the same way):

```sh
file=photos/cat.jpg
snapshot=$(wrt-snap list shares | tail -n 1)
cp -a "${snapshot}/${file}" "/mnt/data/shares/${file}"
```

A whole directory comes back the same way with `cp -a` of the directory.

### An enclosure that drops out

The R4S's USB 3 port runs the disk with UAS. Some USB-to-SATA bridges reset under load in that mode (the kernel log shows `uas_eh_abort_handler` or `reset SuperSpeed USB device` over and over). Such an enclosure works with the older, slower mass storage protocol (BOT) instead: give `usb-storage` a quirk for its USB ID (from `/sys/bus/usb/devices/*/idVendor` and `idProduct`, e.g. `152d:0578`) with the flag `u`, which ignores UAS, and keep the file through upgrades:

```sh
echo 'options usb-storage quirks=152d:0578:u' >>/etc/modules.conf
echo /etc/modules.conf >>/etc/sysupgrade.conf
reboot
```

## Containers

podman runs app containers (qBittorrent and the like, never in the image), with crun and netavark. Their storage is on the data disk. Its bridge `podman0` is the fw4 zone `podman`: out to `wan` and in from `lan`, never to `lan`. podman writes no firewall rules of its own (netavark's `firewall_driver = "none"`): containers leave through einat like the LAN, or masquerade when einat is off. dae treats their traffic as it treats the LAN's.

### Declare a Pod

Each app is a Kubernetes Pod in `/mnt/data/containers/pods/<name>.yaml`, named `<name>`. The `wrt-containers` service plays every declaration with `podman kube play` once the data disk is mounted (at boot, or when it is plugged in), and replays one only when it has changed since; an unchanged Pod is started as it is. Every Pod joins podman's network `podman` (10.88.0.0/16 on `podman0`). More options of `podman kube play` go into `<name>.options` next to it, such as a fixed address:

```yaml
# /mnt/data/containers/pods/torrent.yaml
apiVersion: v1
kind: Pod
metadata:
  name: torrent
spec:
  containers:
    - name: qbittorrent
      image: lscr.io/linuxserver/qbittorrent:latest
      volumeMounts:
        - name: downloads
          mountPath: /downloads
        - name: config
          mountPath: /config
  volumes:
    - name: downloads
      hostPath:
        path: /mnt/data/downloads
    - name: config
      hostPath:
        path: /mnt/data/containers/torrent
        type: DirectoryOrCreate
```

```sh
echo --ip=10.88.0.20 >/mnt/data/containers/pods/torrent.options
/etc/init.d/wrt-containers restart
```

### Expose a port

A port reaches a container only through an fw4 port forward to its address, so give the Pod a fixed one (`--ip` above). Keep the outside port out of einat's range, 20000-29999, which einat takes for its own mappings:

```sh
uci -q batch <<'EOF'
set firewall.torrent=redirect
set firewall.torrent.name='torrent'
set firewall.torrent.src='wan'
set firewall.torrent.src_dport='51413'
set firewall.torrent.dest='podman'
set firewall.torrent.dest_ip='10.88.0.20'
set firewall.torrent.dest_port='51413'
set firewall.torrent.proto='tcp udp'
commit firewall
EOF
/etc/init.d/firewall reload
```

The LAN reaches containers at their addresses directly, e.g. `http://10.88.0.20:8080/`.

## File sharing

ksmbd, the kernel's SMB server, shares `/mnt/data/shares` as `shares` on the LAN only: SMB 3.0 at least, a user and password always (an unknown user is refused, never a guest). While the data disk is not mounted it offers nothing and does not run. Share users are system accounts without a login, with an SMB password of their own; none is preset:

```sh
echo 'alice:x:1000:1000::/var:/bin/false' >>/etc/passwd
echo 'alice:x:1000:' >>/etc/group
ksmbd.adduser -a alice          # asks for the password
chown alice:alice /mnt/data/shares
/etc/init.d/ksmbd restart
```

More shares go under `/mnt/data/shares` in `/etc/config/ksmbd` (or LuCI's Network Shares).

## VPN

Two ways in, each an fw4 zone of its own that forwards to `lan` and `wan` and rejects input to the router itself (so SMB, SSH and LuCI stay LAN-only).

- **WireGuard** (`wg0`, in the kernel, UDP 51820, the router is 10.9.0.1/24): the image carries the interface disabled and no keys. The config push writes the private key and the peers (`network.wg0.private_key`, sections `wireguard_wg0`) and sets `network.wg0.disabled=0`. Its traffic bypasses dae: it goes out direct.
- **Tailscale** (`tailscale0`, nftables mode, UDP 41641): log in once with the LAN as a subnet route; the router can also be an exit node. Its traffic goes through dae like the LAN's:

```sh
tailscale up --advertise-routes=10.0.0.0/24 --advertise-exit-node --accept-dns=false
```

Tailscale marks its packets with bits of `0x00ff0000`, which `config/marks.tsv` reserves for it.

## Metrics

The node exporter (prometheus-node-exporter-ucode) answers on the LAN only, at `http://10.0.0.1:9101/metrics`: CPU, memory, network interfaces, filesystems (the SD card's, and the data disk's while mounted) and temperatures (the SoC's, through `rockchip-thermal` and hwmon). It needs no data disk.
