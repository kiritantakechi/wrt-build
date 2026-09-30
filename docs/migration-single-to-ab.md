# From the single-slot image to A/B

The A/B layout (docs/ab-layout.md) changes the partition table, so a system on the single-slot image cannot upgrade into it. Write the factory image once and carry the configuration over by hand; every later upgrade is a single-slot `sysupgrade`.

The factory image goes to the board's boot disk: the NanoPi R4S's SD card, the NanoPi R6S's eMMC. Its name carries the board's OpenWrt device, `friendlyarm_nanopi-r4s` or `friendlyarm_nanopi-r6s`.

1. On the running system, save the configuration and copy it off the router:

   ```sh
   ssh root@10.0.0.1 sysupgrade -b /tmp/backup.tar.gz
   scp -O root@10.0.0.1:/tmp/backup.tar.gz .
   ```

2. Write the factory image to the boot disk:
   - **NanoPi R4S:** write it to the SD card on a computer (check the device name first; this erases the card):

     ```sh
     gzip -dc openwrt-rockchip-armv8-friendlyarm_nanopi-r4s-erofs-factory.img.gz | sudo dd of=/dev/<sd> bs=4M conv=fsync
     ```

   - **NanoPi R6S:** write it to the eMMC from a system on an SD card, or over USB in maskrom mode (below).

3. Boot the board from its boot disk. It starts on slot A with the factory configuration at 10.0.0.1.

4. Restore the configuration and reboot:

   ```sh
   scp -O backup.tar.gz root@10.0.0.1:/tmp/
   ssh root@10.0.0.1 'sysupgrade -r /tmp/backup.tar.gz && reboot'
   ```

   If the backup changes the LAN address, reconnect at the new one.

From here on, upgrade with the board's single-slot image, `openwrt-rockchip-armv8-<device>-erofs-sysupgrade.tar.gz`. To go back to the previous version, run `wrt-slot switch`, or let U-Boot roll back on its own after three failed boots.

## The NanoPi R6S's eMMC

**From a system on an SD card.** Boot the R6S from an SD card with any Linux system (FriendlyElec's own images will do), copy the factory image onto it, and write the image to the eMMC. The eMMC is the MMC device whose type is `MMC`; an SD card's is `SD`:

```sh
grep . /sys/block/mmcblk*/device/type
gzip -dc openwrt-rockchip-armv8-friendlyarm_nanopi-r6s-erofs-factory.img.gz | dd of=/dev/mmcblk<N> bs=4M conv=fsync
```

Power off, take the SD card out, and power on again: the R6S boots from its eMMC.

**Over USB, in maskrom mode.** When the eMMC holds no loader the boot ROM can run, it waits for a computer on USB. Hold the MASK button while powering the R6S on, connected to the computer as FriendlyElec's wiki shows for maskrom mode. Then write the unpacked factory image with `rkdeveloptool`, which first loads rkbin's RK3588 USB loader (`bin/rk35/rk3588_spl_loader_v<version>.bin`; docs/supply-chain/rkbin.md) into the board:

```sh
gzip -dk openwrt-rockchip-armv8-friendlyarm_nanopi-r6s-erofs-factory.img.gz
rkdeveloptool db rk3588_spl_loader_v<version>.bin
rkdeveloptool wl 0 openwrt-rockchip-armv8-friendlyarm_nanopi-r6s-erofs-factory.img
rkdeveloptool rd
```

**Recovery.** Only a factory image writes U-Boot; an upgrade image never carries it. Should a factory image leave the R6S with a loader or U-Boot that no longer boots, maskrom mode is still there, since the boot ROM offers it whatever the eMMC holds: hold MASK while powering on, and write a working factory image the same way. On the R4S, rewrite the SD card on a computer.
