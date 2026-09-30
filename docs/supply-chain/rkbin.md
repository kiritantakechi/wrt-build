# rkbin: the RK3588's DRAM initialization

Reviewed: 2026-09-30 (board-model task 3.8). The NanoPi R6S's loader holds the one part of either board's boot chain that is built from no source: Rockchip's DRAM initialization for the RK3588, from rkbin. The NanoPi R4S's boot chain is built from source throughout.

| Board | Loader part | Where it comes from |
|---|---|---|
| NanoPi R4S (RK3399) | DRAM initialization (TPL) and SPL | U-Boot 2026.07, from source |
| | TF-A (BL31) | arm-trusted-firmware-rockchip 2.15.0, from source |
| NanoPi R6S (RK3588S) | DRAM initialization, in the TPL's place | rkbin, `rk35/rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.19.bin`: a binary |
| | SPL | U-Boot 2026.07, from source |
| | TF-A (BL31) | arm-trusted-firmware-rockchip 2.15.0, from source |

## Pinned version

Upstream's `package/boot/rkbin` fetches rkbin from https://github.com/rockchip-linux/rkbin at commit `74213af1e952c4683d2e35952507133b61394862` (2025-06-13) and checks the checkout against `PKG_MIRROR_HASH` `4b801b1301ae297f660340617b5f398b23a3f0b43bc7f0ef42c21f0f43eb8990`. `upstream.lock` pins the openwrt tree, and the package with it, so the blob changes only with a bump of openwrt; the bump's drill runs every board, the R6S included.

## Why a binary

- The boot ROM runs it first, from the SoC's own SRAM, before any memory is usable; it trains the memory and hands back to the boot ROM, which then loads U-Boot's SPL.
- Rockchip publishes it as a binary only, and U-Boot has no RK3588 memory initialization of its own. Upstream builds every RK358x board's U-Boot with this blob (`U-Boot/rk358x/Default` in `package/boot/uboot-rockchip`). The RK3399 needs none: U-Boot initializes its memory from source.

## Risks

- **It cannot be reviewed.** It runs before everything else with the SoC to itself, so the boot chain of the R6S is only as trustworthy as Rockchip's build of it.
- **It comes from a vendor repository with binaries of every kind**; only this file of it reaches the image, as `ROCKCHIP_TPL` of the R6S's U-Boot build.
- **It changes silently with upstream.** A bump that moves rkbin changes the R6S's loader; the release notes name the openwrt commit, and the factory image is the only way a new loader reaches a board, since upgrade images carry no U-Boot.

Maskrom recovery (`docs/migration-single-to-ab.md`) uses another rkbin binary, the RK3588 USB loader, on the computer that flashes the board; it never reaches the image.
