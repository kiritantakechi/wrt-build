# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Complete R4S boot chain`
- TO: `### Requirement: Complete boot chain`

## MODIFIED Requirements

### Requirement: Complete boot chain
The factory image the build produces SHALL carry everything its board needs to boot it with no manual steps:
- at sector 64, the loader of the board's SoC: the RK3399 loader for the NanoPi R4S, the RK3588 loader with its DDR initialization for the NanoPi R6S;
- at sector 16384, a U-Boot FIT for the board with TF-A, whose built-in environment holds the slot logic.

Each slot's boot partition SHALL hold a kernel FIT whose default configuration carries the board's device tree, with all of its network ports enabled. There is no boot script: the slot logic lives in the bootloader (firmware/boot-rollback). The emulator runs the kernel and root filesystem of this image through a U-Boot built for QEMU; this requirement covers the parts that only the board's SoC can run.

#### Scenario: Inspect the boot chain
- **WHEN** the factory image is inspected
- **THEN**:
  - sector 64 holds a loader for the board's SoC;
  - sector 16384 holds a U-Boot FIT whose default configuration is compatible with the board's name, loads TF-A and boots with `run wrt_boot`;
  - the kernel FIT on both boot-A and boot-B carries a device tree compatible with the board's name and its SoC, with the board's Ethernet and PCIe controllers enabled
