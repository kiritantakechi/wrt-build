# From the single-slot image to A/B

The A/B layout (docs/ab-layout.md) changes the partition table, so a system on the single-slot image cannot upgrade into it. Write the factory image once and carry the configuration over by hand; every later upgrade is a single-slot `sysupgrade`.

1. On the running system, save the configuration and copy it off the router:

   ```sh
   ssh root@10.0.0.1 sysupgrade -b /tmp/backup.tar.gz
   scp -O root@10.0.0.1:/tmp/backup.tar.gz .
   ```

2. Write the factory image to the SD card (check the device name first; this erases the card):

   ```sh
   gzip -dc openwrt-rockchip-armv8-friendlyarm_nanopi-r4s-erofs-factory.img.gz | sudo dd of=/dev/<sd> bs=4M conv=fsync
   ```

3. Boot the R4S from the card. It starts on slot A with the factory configuration at 10.0.0.1.

4. Restore the configuration and reboot:

   ```sh
   scp -O backup.tar.gz root@10.0.0.1:/tmp/
   ssh root@10.0.0.1 'sysupgrade -r /tmp/backup.tar.gz && reboot'
   ```

   If the backup changes the LAN address, reconnect at the new one.

From here on, upgrade with the single-slot image, `openwrt-rockchip-armv8-friendlyarm_nanopi-r4s-erofs-sysupgrade.tar.gz`. To go back to the previous version, run `wrt-slot switch`, or let U-Boot roll back on its own after three failed boots.
