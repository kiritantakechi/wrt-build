"""firmware/rootfs: the R4S boot chain, then an EROFS root with a zstd f2fs overlay."""

import re
from typing import TYPE_CHECKING

from wrt_tests import spec
from wrt_tests.emu import (
    BOARD_COMPATIBLE,
    BOOT_PARTITION,
    boot_files,
    extract_fit_image,
    read_fit,
    run,
)
from wrt_tests.image import SECTOR, read_mbr, script_text

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.router import Router

CAPABILITY = "firmware/rootfs"
# Digest of every file of the read-only root, independent of the overlay above it.
ROM_DIGEST = "find /rom -xdev -type f | sort | xargs sha256sum | sha256sum"
# The RK3399 boot ROM reads the loader (TPL and SPL) from sector 64 of the SD card,
# and SPL reads the U-Boot FIT from sector 16384.
LOADER_SECTOR, UBOOT_SECTOR = 64, 16384
SOC_COMPATIBLE = "rockchip,rk3399"
# The script finds the root on partition 2 and loads the kernel FIT from partition 1
# of the device it was itself loaded from, then boots it.
BOOT_SCRIPT_STEPS = (
    r"^part uuid \$\{devtype\} \$\{devnum\}:2 uuid$",
    r"^load \$\{devtype\} \$\{devnum\}:1 \$\{kernel_addr_r\} kernel\.img$",
    r"^bootm \$\{kernel_addr_r\}$",
)
# The two ports: the GMAC (WAN, eth0) and the PCIe controller of the RTL8111 (LAN, eth1).
PORT_NODES = ("/ethernet@fe300000", "/pcie@f8000000")


def _sectors(disk: Path, start: int, end: int, output: Path) -> Path:
    """Copy sectors ``start`` up to ``end`` of a raw disk into ``output``."""
    with disk.open("rb") as raw:
        raw.seek(start * SECTOR)
        output.write_bytes(raw.read((end - start) * SECTOR))
    return output


def _mount(router: Router, mountpoint: str) -> tuple[str, str, str]:
    """Return (source, type, options) of a mount point."""
    line = router.run(f"awk '$2 == \"{mountpoint}\"' /proc/mounts")
    source, _, kind, options, *_ = line.split()
    return source, kind, options


@spec(CAPABILITY, "EROFS root filesystem", "Check build artifacts")
def test_build_outputs_are_erofs(build_output: Path) -> None:
    images = sorted(p.name for p in (build_output / "targets").glob("*.img*"))
    assert images
    assert all("-erofs-" in name for name in images), images
    assert not [name for name in images if "squashfs" in name or "ext4" in name]


@spec(CAPABILITY, "EROFS root filesystem", "Check mounts on the router")
def test_rom_is_erofs(router: Router) -> None:
    _, kind, options = _mount(router, "/rom")
    assert kind == "erofs"
    assert options.split(",")[0] == "ro"


@spec(CAPABILITY, "Writable layer is zstd-compressed f2fs", "First boot creates the overlay")
def test_overlay_is_compressed_f2fs(router: Router) -> None:
    source, kind, options = _mount(router, "/overlay")
    assert kind == "f2fs"
    assert re.search(r"(^|,)compress_algorithm=zstd(:\d+)?(,|$)", options), options
    # The overlay is a loop device on the root partition itself, past the EROFS image.
    # fstools opens the partition during preinit, from a /dev that is mounted
    # elsewhere later, so the recorded path may lack the /dev prefix.
    loop = source.removeprefix("/dev/")
    backing = router.run(f"cat /sys/block/{loop}/loop/backing_file")
    assert re.fullmatch(r"(/dev)?/(vda|mmcblk\d+p)2", backing), backing
    assert int(router.run(f"cat /sys/block/{loop}/loop/offset")) > 0


@spec(CAPABILITY, "Factory reset clears only the writable layer", "Factory reset")
def test_factory_reset_only_clears_the_overlay(router: Router) -> None:
    rom = router.run(ROM_DIGEST)
    router.run("uci set system.@system[0].hostname=changed && uci commit system")
    router.run("touch /root/user-file && sync")
    router.reboot("firstboot -y && reboot")
    assert router.run("uci get system.@system[0].hostname") == "OpenWrt"
    assert router.returncode("[ -e /root/user-file ]") != 0
    assert router.run(ROM_DIGEST) == rom
    assert _mount(router, "/overlay")[1] == "f2fs"


@spec(CAPABILITY, "Complete R4S boot chain", "Inspect the boot chain")
def test_boot_chain(emulation_dir: Path, tmp_path: Path) -> None:
    disk = emulation_dir / "disk.raw"
    with disk.open("rb") as raw:
        boot_start = read_mbr(raw.read(SECTOR)).partition(BOOT_PARTITION).start // SECTOR
    loader = _sectors(disk, LOADER_SECTOR, UBOOT_SECTOR, tmp_path / "idbloader.img")
    assert "Rockchip RK33 (SD/MMC) boot image" in run("dumpimage", "-T", "rksd", "-l", str(loader))

    uboot = read_fit(_sectors(disk, UBOOT_SECTOR, boot_start, tmp_path / "u-boot.itb"))
    assert uboot.configuration["Compatible"] == BOARD_COMPATIBLE
    assert uboot.selected("Firmware")["OS"] == "ARM Trusted Firmware"
    assert "u-boot" in uboot.configuration.properties["Loadables"]

    boot_files(disk, ("boot.scr", "kernel.img"), tmp_path)
    script = script_text((tmp_path / "boot.scr").read_bytes())
    for step in BOOT_SCRIPT_STEPS:
        assert re.search(step, script, re.MULTILINE), step
    kernel, dtb = tmp_path / "kernel.img", tmp_path / "board.dtb"
    extract_fit_image(kernel, read_fit(kernel).selected("FDT"), dtb)
    assert run("fdtget", str(dtb), "/", "compatible").split() == [BOARD_COMPATIBLE, SOC_COMPATIBLE]
    for node in PORT_NODES:
        assert run("fdtget", str(dtb), node, "status").strip() == "okay", node
