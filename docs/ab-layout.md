# A/B slots

The boot disk holds two complete systems, slot A and slot B: the SD card on the NanoPi R4S, the eMMC on the NanoPi R6S. The layout is the same on both. U-Boot boots the slot named by `boot_slot`; an upgrade writes the other slot and makes it a trial slot, which the health check confirms or U-Boot rolls back (r4s-ab-rollback).

## Layout

| Offset | Content | Size |
|---|---|---|
| `0x8000` | idbloader: the SoC's loader (TPL and SPL on the RK3399; rkbin's DRAM initialization and SPL on the RK3588S) | < 4 MiB |
| `0x3F8000` | U-Boot environment, first copy | 32 KiB |
| `0x400000` | U-Boot environment, second copy | 32 KiB |
| `0x800000` | u-boot.itb (U-Boot + TF-A) | < 24 MiB |
| 32 MiB | p1 boot-A (ext4: `kernel.img`, the configuration handed over on upgrade) | 64 MiB |
| | p2 root-A (EROFS, then its f2fs overlay from the next 64 KiB boundary) | 1024 MiB |
| | p3 boot-B | 64 MiB |
| | p4 root-B | 1024 MiB |

The whole image is 2.2 GiB, so any 4 GB SD card holds it; on the R6S's 32 GB eMMC the rest stays unused. U-Boot is shared by both slots and only changes when the factory image is written again.

## Variables

U-Boot reads only these three from the stored environment; the logic that uses them is built into U-Boot (`uboot/wrt-ab.env`).

| Variable | Meaning |
|---|---|
| `boot_slot` | `a` or `b`: the slot to boot. Missing or anything else means `a`. |
| `upgrade_available` | `1` while the slot is on trial, `0` or missing once it is confirmed. |
| `bootcount` | Boots of the trial slot so far; U-Boot counts and saves it only while `upgrade_available` is 1. |

`bootlimit` is 3 and built in. Linux reads and writes the variables with `fw_printenv` and `fw_setenv`; `wrt-slot status` shows them.

The environment is stored twice. Each write, U-Boot's or Linux's, replaces the older copy and gives it a serial flag one higher, and U-Boot reads the valid copy with the higher flag; with neither valid, it uses its built-in default, which boots slot A. A reset in the middle of a write, by a power cut or the watchdog, so leaves the previous state in effect. U-Boot names its copies on the kernel command line, `wrt.env=0x8000@0x3F8000,0x8000@0x400000` (size and offset of each), next to `wrt.slot=`, and the system configures `fw_printenv` and `fw_setenv` from that alone (`31-wrt-ab`). A U-Boot that names none predates the second copy: the system then leaves the environment alone, and an upgrade refuses until the factory image is written, which brings the new U-Boot.

## States

```
confirmed ──sysupgrade / wrt-slot switch──▶ trial of the other slot
trial ──health check passes──▶ confirmed (this slot)
trial ──health check fails, panic or watchdog: reboot──▶ trial, bootcount + 1
trial ──4th unconfirmed boot (bootcount > 3)──▶ U-Boot switches back: confirmed (the previous slot)
```

Within one power cycle U-Boot also falls back to the other slot when a slot's kernel does not load; if neither loads, it stops at its prompt instead of looping.

## Recovering by hand over the serial console

Connect to the board's debug UART (1500000 baud on both boards; the emulator's console is the PL011), press a key while U-Boot counts down, and make a slot the confirmed one:

```
=> setenv boot_slot a
=> setenv upgrade_available 0
=> setenv bootcount 0
=> saveenv
=> run wrt_boot
```

Replace `a` with `b` for slot B. From a running system, `wrt-slot switch` does the same for the other slot, as a trial that the health check confirms.
