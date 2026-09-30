# Tasks

## 1. Kernel and emulation environment (design D10)

- [x] 1.1 Add `CONFIG_USB_PCI=y` and `CONFIG_USB_XHCI_PCI=y` to the virt driver group in `config/kernel.config`, and fill in the sub-options with `listnewconfig`. Verification: the built kernel config passes validation; in the emulator the xHCI controller's two root hubs are registered (the image has no `lsusb`; the hot-plug self-test reads them from sysfs).
- [x] 1.2 Extend the emulator fixture: attach `qemu-xhci`; use `usb-uas` plus `scsi-hd` for the data disk; plug and unplug disks on a given port through QMP `device_add` and `device_del` (a hot-plugged `usb-uas` waits for its disk and appears on the port only when its `attached` property is set). Verification: a new self-test in `tests/testing/test_emulation.py` (scenario "Hot-plug a USB disk" of the testing/emulation delta) confirms that a hot-plugged disk is bound to the uas driver at SuperSpeed, and that the device disappears after removal.
- [x] 1.3 In `wrt_tests/`, implement the test CA and a tool that assembles an OCI image from programs of the shipped rootfs (busybox, uhttpd, uclient-fetch and the libraries their ELF headers name); run a distribution registry and headscale (with embedded DERP) in `inet`; add two namespaces, `wg-peer` (a wireguard link of the host kernel, whose module `sandbox-prepare` loads) and `ts-peer`. Add the related tools (distribution, skopeo, samba's smbclient, wireguard-tools, headscale, tailscale, curl, openssl) to the flake's test tool group. Verification: `tests/unit/test_oci.py` inspects the generated image with skopeo on the host and confirms the architecture is arm64 and its contents; `tests/unit/test_net.py` confirms that the new namespaces have correct addresses and routes.

## 2. Data disk

- [x] 2.1 Add `config/services.seed` with the contents listed in design D9. Verification: the line-by-line check in `just config ci` passes; `just image-audit` finds the services' packages and no app of a container.
- [x] 2.2 Implement `wrt-data init` in the own feed: list candidate disks and require typing the full device name to confirm; then create the btrfs filesystem and subvolumes, name the disk by UUID in the fstab entry the image holds from its first boot, and mount it by the hotplug path. Verification: `test_data_disk.py` runs initialization on a blank disk and reboots, covering the "Check mounts" scenario, in which a second blank disk is left untouched (no block of its image written) when the confirmation is wrong.
- [x] 2.3 Set up persistent logs: `log_file=/mnt/data/logs/messages`, `log_size=64M`; the log service writes the file only while the data disk is mounted, at boot and after (`patches/openwrt/0009`). Verification: covered by the "View logs after reboot" test; the "Boot without the data disk" test confirms that this log file does not appear on the SD card when no data disk is attached.
- [x] 2.4 Implement `wrt-snap` `now`, `prune` (the last seven days, today's included) and `list` in the own feed, plus a daily cron job. Verification: covered by the tests for the three snapshot scenarios (expiry pruning is tested by advancing the system clock one day at a time, to just before the job, and letting cron run it).

## 3. Startup ordering for mount-dependent services and degraded mode

- [x] 3.1 Add `procd_add_restart_mount_trigger` to the `wrt-containers` and ksmbd init scripts (ksmbd through `patches/packages/0001`), and return immediately when the mount point is absent; podman's own API service stays disabled. Verification: covered by the "Data disk mounts late" test (the disk is inserted through QMP after a boot without it).
- [x] 3.2 Degraded behavior. Verification: covered by the "Boot without the data disk" test, which reuses the datapath probes to confirm that the LAN has internet access and the proxy works, and confirms that the A/B health check passes.

## 4. Containers

- [x] 4.1 Modify `containers.conf` to set `firewall_driver = "none"`; modify `storage.conf` to put graphroot on the data disk. Verification: covered by the "Pull an image" and "Check the ruleset" tests.
- [x] 4.2 Add the fw4 `podman` zone and forwarding rules through uci-defaults, and verify that einat's internal network setting includes the container subnet (einat translates every internal source). Verification: covered by the "Container reaches the internet" test, in which the container uses busybox `nc` to reach a probe address and the public port seen lies in einat's range, which masquerade would not choose (busybox's `nc` in the image cannot pick its source port); the "Check the ruleset" test confirms that the LAN can reach containers and that containers cannot reach the LAN.
- [x] 4.3 Write an example fw4 redirect (a container port exposed to the WAN, outside 20000-29999). Verification: covered by the "Expose a container port" test, accessed from `inet`.
- [x] 4.4 Implement `wrt-containers` in the own feed: iterate over `pods/*.yaml` (and each one's optional `.options`, more options of `podman kube play` such as `--ip`), compare hashes, then run `podman kube play --replace`, with a mount trigger on the data disk. Verification: covered by the "Start on boot" and "Declaration unchanged" tests (the latter compares container IDs).
- [x] 4.5 Container traffic goes through the proxy. Verification: covered by the "Container reaches a proxied target" test; the test also confirms that once podman0 appears, dae attaches its programs to it.

## 5. File sharing

- [x] 5.1 Configure ksmbd through uci-defaults: bind only to lan, minimum protocol SMB 3.0, no guest access (an unknown user is refused, not mapped to guest), shares under `/mnt/data/shares`; fw4 allows 445 only on lan. Verification: covered by all tests of the file-sharing spec, which connect with smbclient from `client-a`, `inet`, `wg-peer`, and `ts-peer`; SMB1 negotiation is forced with `client max protocol = NT1`.

## 6. VPN

- [x] 6.1 Configure WireGuard: wg0 in the `wg` zone, with no preset keys. Verification: covered by the "Remote device connects" and "WireGuard device reaches the internet" tests, with `wg-peer` as the peer.
- [x] 6.2 Configure Tailscale: nftables mode, advertising the LAN subnet route; verify the marks used in the tailscale source and register them in `config/marks.tsv`. Verification: covered by the "Reach the LAN via subnet route", "Tailnet device reaches a proxied target", and "Check the allocation table" tests, with `ts-peer`, logged into headscale, as the peer.

## 7. Monitoring

- [x] 7.1 Configure node-exporter: `listen_interface 'lan'`, with the cpu, meminfo, netdev, filesystem, and hwmon collectors enabled (`wrt-metrics` adds the last two; the filesystem collector reads the host's mounts through its rpcd plugin, as the exporter's jail sees none). Verification: covered by the monitoring spec tests; the temperature scenario checks that `rockchip-thermal` is registered and the hwmon collector succeeds.

## 8. Emulator tests (all run in `just test`)

- [x] 8.1 `tests/storage/test_data_disk.py`: covers all scenarios of the data-disk spec. Verification: all tests pass.
- [x] 8.2 `tests/services/test_containers.py`: covers all scenarios of the containers spec; the "Check the image" scenario reads the package list of the running image with apk, and `just image-audit` checks the built image the same way. Verification: all tests pass.
- [x] 8.3 `tests/services/test_file_sharing.py`, `test_vpn.py`, `test_monitoring.py`: cover all scenarios of the corresponding specs. Verification: all tests pass; `spec-coverage` shows no uncovered scenario in this change.

## 9. Documentation

- [x] 9.1 Write `docs/services.md`: data disk initialization, how to write Pod declaration files, how to expose ports with fw4, the steps to restore from a snapshot, and the `usb-storage` quirk that drops an unstable enclosure back to BOT mode. Verification: the "Restore a file from a snapshot" test in `test_data_disk.py` runs exactly the commands from the document, and the test passes.
