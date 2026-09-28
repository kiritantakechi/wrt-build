# A/B slots

The SD card holds two complete systems, slot A and slot B. U-Boot boots the slot named by `boot_slot`; an upgrade writes the other slot and makes it a trial slot, which the health check confirms or U-Boot rolls back (r4s-ab-rollback).

## Layout

| Offset | Content | Size |
|---|---|---|
| `0x8000` | idbloader (TPL + SPL) | < 4 MiB |
| `0x3F8000` | U-Boot environment | 32 KiB |
| `0x800000` | u-boot.itb (U-Boot + TF-A) | < 24 MiB |
| 32 MiB | p1 boot-A (ext4: `kernel.img`, the configuration handed over on upgrade) | 64 MiB |
| | p2 root-A (EROFS, then its f2fs overlay from the next 64 KiB boundary) | 1024 MiB |
| | p3 boot-B | 64 MiB |
| | p4 root-B | 1024 MiB |

The whole card is 2.2 GiB, so any 4 GB card holds it. U-Boot is shared by both slots and only changes when the factory image is written again.

## Variables

U-Boot reads only these three from the stored environment; the logic that uses them is built into U-Boot (`uboot/wrt-ab.env`).

| Variable | Meaning |
|---|---|
| `boot_slot` | `a` or `b`: the slot to boot. Missing or anything else means `a`. |
| `upgrade_available` | `1` while the slot is on trial, `0` or missing once it is confirmed. |
| `bootcount` | Boots of the trial slot so far; U-Boot counts and saves it only while `upgrade_available` is 1. |

`bootlimit` is 3 and built in. Linux reads and writes the variables with `fw_printenv` and `fw_setenv`; `wrt-slot status` shows them.

## States

```
confirmed ──sysupgrade / wrt-slot switch──▶ trial of the other slot
trial ──health check passes──▶ confirmed (this slot)
trial ──health check fails, panic or watchdog: reboot──▶ trial, bootcount + 1
trial ──4th unconfirmed boot (bootcount > 3)──▶ U-Boot switches back: confirmed (the previous slot)
```

Within one power cycle U-Boot also falls back to the other slot when a slot's kernel does not load; if neither loads, it stops at its prompt instead of looping.

## Recovering by hand over the serial console

Connect to the R4S debug UART (1500000 baud; the emulator's console is the PL011), press a key while U-Boot counts down, and make a slot the confirmed one:

```
=> setenv boot_slot a
=> setenv upgrade_available 0
=> setenv bootcount 0
=> saveenv
=> run wrt_boot
```

Replace `a` with `b` for slot B. From a running system, `wrt-slot switch` does the same for the other slot, as a trial that the health check confirms.
