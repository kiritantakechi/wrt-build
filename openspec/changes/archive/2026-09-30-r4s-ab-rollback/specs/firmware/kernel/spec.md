# Spec Delta

## MODIFIED Requirements

### Requirement: Same kernel boots in the emulator
The kernel SHALL build in the drivers the QEMU `virt` platform needs: PL011 serial, the generic PCIe host controller, an SD host controller on PCI (sdhci-pci) for the SD card, virtio network devices, and the i6300esb watchdog. The shipped kernel then boots in the emulator without modification and uses the SD card, network, and watchdog. These drivers MUST be built into the kernel, not as modules.

#### Scenario: Shipped kernel boots in the emulator
- **WHEN** the emulator's U-Boot boots the kernel of the shipped factory image
- **THEN** the serial console produces output, the root filesystem on the SD card is mounted, and both virtio NICs and the watchdog device are detected
