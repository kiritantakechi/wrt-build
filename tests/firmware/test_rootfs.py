"""firmware/rootfs: the board's boot chain, then an EROFS root with a zstd f2fs overlay."""

import re
from typing import TYPE_CHECKING

from wrt_tests import spec
from wrt_tests.emu import boot_files, extract_fit_image, read_fit, run
from wrt_tests.image import SECTOR, default_environment, read_mbr

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.boards import Board
    from wrt_tests.router import Router

CAPABILITY = "firmware/rootfs"
# Digest of every file of the read-only root, independent of the overlay above it.
ROM_DIGEST = "find /rom -xdev -type f | sort | xargs sha256sum | sha256sum"
# The SoC's boot ROM reads the loader (DRAM setup and SPL) from sector 64 of the
# boot disk, and SPL reads the U-Boot FIT from sector 16384.
LOADER_SECTOR, UBOOT_SECTOR = 64, 16384
# boot-A and boot-B, each with the kernel FIT of its slot.
BOOT_PARTITIONS = (1, 3)
# What the slot logic (uboot/wrt-ab.env) runs besides the command that starts
# the kernel: part uuid, load from the ext4 boot partition, and saveenv to the
# environment on the boot disk, where bootcount lives too.
SLOT_LOGIC = (
    "CONFIG_CMD_PART",
    "CONFIG_PARTITION_UUIDS",
    "CONFIG_CMD_FS_GENERIC",
    "CONFIG_FS_EXT4",
    "CONFIG_CMD_SAVEENV",
    "CONFIG_ENV_IS_IN_MMC",
    "CONFIG_BOOTCOUNT_ENV",
)


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
    images = sorted(p.name for p in (build_output / "targets").glob("*.gz"))
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


@spec(CAPABILITY, "Complete boot chain", "Inspect the boot chain")
def test_boot_chain(board: Board, build_output: Path, emulation_dir: Path, tmp_path: Path) -> None:
    disk = emulation_dir / "disk.raw"
    with disk.open("rb") as raw:
        first = read_mbr(raw.read(SECTOR)).partitions[0].start // SECTOR
    # The boot ROM of the board's SoC takes the loader by its signature; U-Boot's
    # own tool verifies the loader's header.
    idbloader = _sectors(disk, LOADER_SECTOR, UBOOT_SECTOR, tmp_path / "idbloader.img")
    run("dumpimage", "-T", "rksd", "-l", str(idbloader))
    header, loader = board.soc.loader, idbloader.read_bytes()
    assert (
        loader[header.offset : header.offset + len(header.signature)] == header.signature.encode()
    )

    itb = _sectors(disk, UBOOT_SECTOR, first, tmp_path / "u-boot.itb")
    uboot = read_fit(itb)
    assert uboot.configuration["Compatible"] == board.board_name
    assert uboot.selected("Firmware")["OS"] == "ARM Trusted Firmware"
    assert "u-boot" in uboot.configuration.properties["Loadables"]
    extract_fit_image(itb, uboot.images["u-boot"], tmp_path / "u-boot.bin")
    environment = default_environment((tmp_path / "u-boot.bin").read_bytes(), "wrt_boot")
    assert environment["bootcmd"] == "run wrt_boot"
    # It has what the slot logic runs on the board itself.
    config = (build_output / "u-boot.config").read_text().splitlines()
    enabled = {line.removesuffix("=y") for line in config if line.endswith("=y")}
    start = f"CONFIG_CMD_{environment['wrt_bootos'].split()[0].upper()}"
    assert {*SLOT_LOGIC, start} <= enabled, {*SLOT_LOGIC, start} - enabled

    for partition in BOOT_PARTITIONS:
        slot = tmp_path / f"boot-{partition}"
        slot.mkdir()
        boot_files(disk, partition, ("kernel.img",), slot)
        kernel, dtb = slot / "kernel.img", slot / "board.dtb"
        extract_fit_image(kernel, read_fit(kernel).selected("FDT"), dtb)
        compatible = run("fdtget", str(dtb), "/", "compatible").split()
        assert compatible == [board.board_name, board.soc.compatible], partition
        # The board's Ethernet and PCIe controllers.
        for node in board.dt_enabled:
            assert run("fdtget", str(dtb), node, "status").strip() == "okay", (partition, node)
