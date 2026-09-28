# r4s-build-foundation validation

## Automated

Every foundation spec scenario maps to a test, or is registered in `tests/verified-elsewhere.toml` as verified elsewhere, together with the build or CI job that verifies it. The tool output is authoritative for this mapping, and no separate table is kept here:

```sh
nix develop -c sh -c 'cd tests && uv run spec-coverage --change r4s-build-foundation'
```

Run all tests in the emulator against the shipped image of a build (in the local VM or the CI `system-test` job):

```sh
nix develop -c just test dev      # or: just test ci
```

The report is written to `tests/.reports/emulation.xml`.

## On the device

This takes a single command. First write the image to a microSD card (double-check the device name before writing):

```sh
gzip -dc openwrt-rockchip-armv8-friendlyarm_nanopi-r4s-erofs-sysupgrade.img.gz | sudo dd of=/dev/<sd> bs=4M conv=fsync
```

Connect the computer to the R4S LAN port (the one next to the USB ports), get an address via DHCP, then run on macOS or in the VM:

```sh
just test-device 10.0.0.1
```

Emulator-only tests (power loss, the failsafe button, factory reset, upgrades: operations that change device state) show up as skipped on the device, with the reason. The only device-only scenario is "boot after flashing": booting from the SD card through U-Boot to userspace, with the management UI reachable on the LAN.

The report is written to `tests/.reports/device.xml`, and the results are archived in `docs/validation/foundation-device.md`.
