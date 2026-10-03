# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Drivers for the R4S ports`
- TO: `### Requirement: Drivers for the board's ports`

## MODIFIED Requirements

### Requirement: Same kernel boots in the emulator
The kernel SHALL build in the drivers the QEMU `virt` platform needs:
- PL011 serial;
- the generic PCIe host controller;
- an SD host controller on PCI (sdhci-pci) for the boot disk, whether an SD card or an eMMC;
- virtio network devices;
- the i6300esb watchdog.

The shipped kernel then boots in the emulator without modification and uses the boot disk, the network and the watchdog. These drivers MUST be built into the kernel, not as modules.

#### Scenario: Shipped kernel boots in the emulator
- **WHEN** the emulator's U-Boot boots the kernel of the shipped factory image
- **THEN** the serial console produces output, the root filesystem on the boot disk is mounted, and every virtio NIC and the watchdog device are detected

### Requirement: Drivers for the board's ports
The kernel SHALL register the drivers of all of the board's network ports at boot, with no manual step:
- on the NanoPi R4S: the Rockchip GMAC driver (dwmac-rk) for its 1 GbE WAN port, and the RTL8111 driver (r8169) for its LAN port behind the RK3399 PCIe host controller (pcie-rockchip-host);
- on the NanoPi R6S: the Rockchip GMAC driver for its 1 GbE port, and the RTL8125 driver (r8169) for its two 2.5 GbE ports behind the RK3588 DesignWare PCIe host controllers (pcie-dw-rockchip).

The emulator has none of these devices, so the drivers are checked while they wait for their devices.

#### Scenario: Port drivers registered
- **WHEN** the drivers registered with the kernel are listed after boot
- **THEN** the platform bus lists the Rockchip GMAC driver and the board's PCIe host controller driver, and the PCI bus lists the r8169 driver
