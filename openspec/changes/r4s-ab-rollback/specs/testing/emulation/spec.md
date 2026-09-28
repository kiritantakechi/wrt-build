# Spec Delta

## MODIFIED Requirements

### Requirement: Boot the shipped artifacts
The emulator SHALL boot the shipped factory image itself, through the bootloader chain:
- the firmware is `uboot-wrt-qemu`, built from the same U-Boot source and slot logic as the R4S bootloader (firmware/boot-rollback);
- the SD card is this image, attached through an SD host controller, so U-Boot and Linux both see an MMC device and the U-Boot environment sits at the same offset as on the R4S;
- U-Boot selects the slot, loads that slot's kernel FIT and passes the kernel command line, as on the R4S.

The emulator MUST NOT use a separately built kernel or root filesystem, and MUST NOT pass a kernel or kernel command line to QEMU itself.

#### Scenario: Verify artifact provenance
- **WHEN** an emulation run starts
- **THEN** the log records the sha256 of the image and of the emulator's U-Boot, and they match the values in the build manifest; the running kernel is the one in the current slot's kernel FIT, and its command line carries `wrt.slot=a` and `fstools_overlay_compression_type=zstd`
