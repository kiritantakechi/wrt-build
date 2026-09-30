# Spec Delta

## MODIFIED Requirements

### Requirement: Complete R4S boot chain
The factory image the build produces SHALL carry everything the NanoPi R4S 4GB needs to boot it with no manual steps: the RK3399 loader at sector 64, and at sector 16384 a U-Boot FIT for the R4S with TF-A whose built-in environment holds the slot logic. Each slot's boot partition SHALL hold a kernel FIT whose default configuration carries the R4S device tree with both network ports enabled. There is no boot script: the slot logic lives in the bootloader (firmware/boot-rollback). The emulator runs the kernel and root filesystem of this image through a U-Boot built for QEMU; this requirement covers the parts that only the RK3399 can run.

#### Scenario: Inspect the boot chain
- **WHEN** the factory image is inspected
- **THEN** sector 64 holds an RK3399 SD boot loader; sector 16384 holds a U-Boot FIT whose default configuration is compatible with `friendlyarm,nanopi-r4s`, loads TF-A and boots with `run wrt_boot`; and the kernel FIT on both boot-A and boot-B carries a device tree compatible with `friendlyarm,nanopi-r4s` and `rockchip,rk3399`, with the GMAC and the PCIe controller enabled
