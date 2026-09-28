# Tasks

## 1. Kernel and emulation environment (design D10)

- [ ] 1.1 Add `CONFIG_USB_PCI=y` and `CONFIG_USB_XHCI_PCI=y` to the virt driver group in `config/kernel.config`, and fill in the sub-options with `listnewconfig`. Verification: the built kernel config passes validation; `lsusb -t` in the emulator shows the xHCI root hub.
- [ ] 1.2 Extend the emulator fixture: attach `qemu-xhci`; use `usb-uas` plus `scsi-hd` for the data disk; plug and unplug disks on a given port through QMP `device_add` and `device_del`. Verification: a new self-test in `tests/testing/test_emulation.py` confirms that a hot-plugged disk uses the uas driver according to dmesg, and that the device disappears after removal.
- [ ] 1.3 In `wrt_tests/`, implement the test CA and a tool that assembles an OCI image from busybox and musl in the shipped rootfs; run a distribution registry and headscale (with embedded DERP) in `inet`; add two namespaces, `wg-peer` and `ts-peer`. Add the related tools (distribution, skopeo, samba's smbclient, wireguard-go, wireguard-tools, headscale, tailscale, curl) to the flake's test tool group. Verification: `tests/unit/test_oci.py` inspects the generated image with skopeo on the host and confirms the architecture is arm64; `tests/unit/test_net.py` confirms that the new namespaces have correct addresses and routes.

## 2. Data disk

- [ ] 2.1 Add `config/services.seed` with the contents listed in design D9. Verification: the line-by-line check in `just config ci` passes.
- [ ] 2.2 Implement `wrt-data init` in the own feed: list candidate disks and require typing the full device name to confirm; then create the btrfs filesystem and subvolumes and write the UCI fstab. Verification: `test_data_disk.py` runs initialization on a blank disk and reboots, covering the "Check mounts" scenario; another test confirms that the disk is left untouched when no confirmation is entered.
- [ ] 2.3 Set up persistent logs: `log_file=/mnt/data/logs/messages`, `log_size=64M`. Verification: covered by the "View logs after reboot" test; another test confirms that this log file does not appear on the SD card when no data disk is attached.
- [ ] 2.4 Implement `wrt-snap` `now` and `prune` in the own feed, plus a daily cron job. Verification: covered by the tests for the two snapshot scenarios (expiry pruning is tested by advancing the system clock one day at a time).

## 3. Startup ordering for mount-dependent services and degraded mode

- [ ] 3.1 Add `procd_add_restart_mount_trigger` to the podman, `wrt-containers`, and ksmbd init scripts, and return immediately when the mount point is absent. Verification: covered by the "Data disk mounts late" test (the disk is inserted through QMP 30 seconds after boot).
- [ ] 3.2 Degraded behavior. Verification: covered by the "Boot without the data disk" test, which reuses the datapath probes to confirm that the LAN has internet access and the proxy works, and confirms that the A/B health check passes.

## 4. Containers

- [ ] 4.1 Modify `containers.conf` to set `firewall_driver = "none"`; modify `storage.conf` to put graphroot on the data disk. Verification: covered by the "Pull an image" and "Check the ruleset" tests.
- [ ] 4.2 Add the fw4 `podman` zone and forwarding rules through uci-defaults, and verify that einat's internal network setting includes the container subnet. Verification: covered by the "Container reaches the internet" test, in which the container uses busybox `nc` to reach two probe addresses in turn from the same source port and sees the same public port (proving the traffic went through einat); two more tests confirm that the LAN can reach containers and that containers cannot reach the LAN.
- [ ] 4.3 Write an example fw4 redirect (a container port exposed to the WAN, outside 20000-29999). Verification: covered by the "Expose a container port" test, accessed from `inet`.
- [ ] 4.4 Implement `wrt-containers` in the own feed: iterate over `pods/*.yaml`, compare hashes, then run `podman kube play --replace`, with a mount trigger on the data disk. Verification: covered by the "Start on boot" and "Declaration unchanged" tests (the latter compares container IDs).
- [ ] 4.5 Container traffic goes through the proxy. Verification: covered by the "Container reaches a proxied target" test; the test also confirms that once podman0 appears, dae attaches its programs to it.

## 5. File sharing

- [ ] 5.1 Configure ksmbd through uci-defaults: bind only to lan, minimum protocol SMB3, no guest access, shares under `/mnt/data/shares`; fw4 allows 445 only on lan. Verification: covered by all tests of the file-sharing spec, which connect with smbclient from `client-a`, `inet`, `wg-peer`, and `ts-peer`; SMB1 negotiation is forced with `client max protocol = NT1`.

## 6. VPN

- [ ] 6.1 Configure WireGuard: wg0 in the `wg` zone, with no preset keys. Verification: covered by the "Remote device connects" and "WireGuard device reaches the internet" tests, with `wg-peer` as the peer.
- [ ] 6.2 Configure Tailscale: nftables mode, advertising the LAN subnet route; verify the marks used in the tailscale source and register them in `config/marks.tsv`. Verification: covered by the "Reach the LAN via subnet route", "Tailnet device reaches a proxied target", and "Check the allocation table" tests, with `ts-peer`, logged into headscale, as the peer.

## 7. Monitoring

- [ ] 7.1 Configure node-exporter: `listen_interface 'lan'`, with the cpu, meminfo, netdev, filesystem, and hwmon collectors enabled. Verification: covered by the monitoring spec tests; the temperature scenario is a device-only test.

## 8. Emulator tests (all run in `just test`)

- [ ] 8.1 `tests/storage/test_data_disk.py`: covers all scenarios of the data-disk spec. Verification: all tests pass.
- [ ] 8.2 `tests/services/test_containers.py`: covers all scenarios of the containers spec; the "Check the image" scenario reads the package list from the image audit output. Verification: all tests pass.
- [ ] 8.3 `tests/services/test_file_sharing.py`, `test_vpn.py`, `test_monitoring.py`: cover all scenarios of the corresponding specs. Verification: all tests pass; `spec-coverage` shows no uncovered scenarios in this change other than the device-only ones.

## 9. Device smoke test and documentation

- [ ] 9.1 Write the `@target("device")` tests: temperature metrics; sustained read/write on the selected SSD and enclosure in UAS mode for 1 hour while downloading at full speed, with no USB resets or UAS errors in dmesg; macOS Finder read/write to shares (the test prompts for manual steps and records the large-file copy throughput). Verification: when run in the emulator, these tests are skipped and show the reason.
- [ ] 9.2 Run `just test-device <host>` and archive the results in `docs/validation/services-device.md`; if UAS is unstable, record the quirks workaround. Verification: the report shows all tests passing.
- [ ] 9.3 Write `docs/services.md`: data disk initialization, how to write Pod declaration files, how to expose ports with fw4, and the steps to restore from a snapshot. Verification: the "Restore a file from a snapshot" test in `test_data_disk.py` runs exactly the commands from the document, and the test passes.
