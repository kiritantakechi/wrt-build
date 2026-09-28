"""Unit tests of wrt_tests.image: reading a sysupgrade image from bytes and listings."""

import gzip
import io
import struct

import pytest

from wrt_tests.image import (
    SECTOR,
    emulator_bootargs,
    gunzip_first_member,
    parse_fit,
    read_mbr,
    script_text,
)

BOOT_SCRIPT = """part uuid ${devtype} ${devnum}:2 uuid
setenv bootargs "console=${serial_port},1500000 earlycon=uart8250,mmio32${serial_addr} \
root=PARTUUID=${uuid} rw rootwait fstools_overlay_compression_type=zstd";
bootm ${kernel_addr_r}
"""


def _mbr(signature: int, partitions: list[tuple[int, int]]) -> bytes:
    disk = bytearray(SECTOR)
    struct.pack_into("<I", disk, 0x1B8, signature)
    for index, (start, sectors) in enumerate(partitions):
        struct.pack_into("<II", disk, 0x1BE + index * 16 + 8, start, sectors)
        disk[0x1BE + index * 16 + 4] = 0x83
    disk[510:512] = b"\x55\xaa"
    return bytes(disk)


def test_gunzip_keeps_the_trailer_apart() -> None:
    source, target = (io.BytesIO(gzip.compress(b"disk" * 1000) + b"FWx0metadata"), io.BytesIO())
    trailer = gunzip_first_member(source, target, chunk=64)
    assert (target.getvalue(), trailer) == (b"disk" * 1000, b"FWx0metadata")


def test_gunzip_rejects_a_truncated_stream() -> None:
    with pytest.raises(ValueError, match="truncated"):
        gunzip_first_member(io.BytesIO(gzip.compress(b"disk" * 100)[:-12]), io.BytesIO())


def test_read_mbr_lists_partitions_and_partuuids() -> None:
    disk = read_mbr(_mbr(0x5452574F, [(65536, 32768), (131072, 2097152)]))
    assert [(p.number, p.start // SECTOR, p.size // SECTOR) for p in disk.partitions] == [
        (1, 65536, 32768),
        (2, 131072, 2097152),
    ]
    assert disk.partuuid(2) == "5452574f-02"


def test_read_mbr_rejects_a_disk_without_boot_signature() -> None:
    with pytest.raises(ValueError, match="MBR"):
        read_mbr(bytes(SECTOR))


def test_script_text_skips_the_legacy_header() -> None:
    body = BOOT_SCRIPT.encode()
    image = bytes(64) + struct.pack(">II", len(body), 0) + body
    assert script_text(image) == BOOT_SCRIPT


def test_emulator_bootargs_rewrites_console_earlycon_and_root() -> None:
    assert emulator_bootargs(BOOT_SCRIPT, "5452574f-02") == (
        "console=ttyAMA0 root=PARTUUID=5452574f-02 rw rootwait "
        "fstools_overlay_compression_type=zstd"
    )


# Shortened ``dumpimage -l`` listings of the two FITs in a shipped image.
KERNEL_FIT = """FIT description: ARM64 OpenWrt FIT (Flattened Image Tree)
 Image 0 (kernel-1)
  Description:  ARM64 OpenWrt Linux-6.18.52
  Type:         Kernel Image
  Compression:  lzma compressed
 Image 1 (fdt-1)
  Type:         Flat Device Tree
 Default Configuration: 'config-1'
 Configuration 0 (config-1)
  Description:  OpenWrt friendlyarm_nanopi-r4s
  Kernel:       kernel-1
  FDT:          fdt-1
"""
UBOOT_FIT = """FIT description: FIT image for U-Boot with bl31 (TF-A)
 Image 0 (u-boot)
  Type:         Standalone Program
 Image 1 (atf-1)
  Type:         Firmware
  OS:           ARM Trusted Firmware
 Default Configuration: 'config-1'
 Configuration 0 (config-1)
  Kernel:       unavailable
  Firmware:     atf-1
  Compatible:   friendlyarm,nanopi-r4s
                rockchip,rk3399
  Loadables:    u-boot
                atf-2
"""


def test_parse_fit_selects_images_by_the_default_configuration() -> None:
    fit = parse_fit(KERNEL_FIT)
    assert (fit.selected("Kernel").index, fit.selected("FDT").index) == (0, 1)
    assert fit.selected("Kernel")["Compression"] == "lzma compressed"


def test_parse_fit_reads_list_properties() -> None:
    fit = parse_fit(UBOOT_FIT)
    assert fit.configuration.properties["Compatible"] == [
        "friendlyarm,nanopi-r4s",
        "rockchip,rk3399",
    ]
    assert fit.configuration.properties["Loadables"] == ["u-boot", "atf-2"]
    assert fit.selected("Firmware")["OS"] == "ARM Trusted Firmware"


def test_parse_fit_rejects_an_unavailable_image() -> None:
    with pytest.raises(LookupError, match="selects no Kernel image"):
        parse_fit(UBOOT_FIT).selected("Kernel")


def test_parse_fit_requires_a_default_configuration() -> None:
    with pytest.raises(LookupError, match="no default configuration"):
        parse_fit(KERNEL_FIT.replace(" Default Configuration: 'config-1'\n", ""))
