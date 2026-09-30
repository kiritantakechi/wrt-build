"""Unit tests of wrt_tests.image: reading a sysupgrade image from bytes and listings."""

import gzip
import io
import struct

import pytest

from wrt_tests.image import (
    SECTOR,
    default_environment,
    gunzip_first_member,
    parse_fit,
    read_mbr,
)


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


# Strings of a U-Boot binary around its built-in environment.
BINARY = (
    b"\x7fELF\x02U-Boot 2026.07\0%s=%s\0\0\x00\x13"
    b"bootcmd=run wrt_boot\0bootlimit=3\0wrt_boot=if test a; then\trun b; fi\0\0"
    b"\xff\xfeother\0\0"
)


def test_default_environment_reads_the_marked_block() -> None:
    assert default_environment(BINARY, "wrt_boot") == {
        "bootcmd": "run wrt_boot",
        "bootlimit": "3",
        "wrt_boot": "if test a; then\trun b; fi",
    }


def test_default_environment_needs_the_marker() -> None:
    with pytest.raises(LookupError, match="wrt_other"):
        default_environment(BINARY, "wrt_other")


# Shortened ``dumpimage -l`` listings of the two FITs in a shipped image, of an example board.
KERNEL_FIT = """FIT description: ARM64 OpenWrt FIT (Flattened Image Tree)
 Image 0 (kernel-1)
  Description:  ARM64 OpenWrt Linux-6.18.52
  Type:         Kernel Image
  Compression:  lzma compressed
 Image 1 (fdt-1)
  Type:         Flat Device Tree
 Default Configuration: 'config-1'
 Configuration 0 (config-1)
  Description:  OpenWrt example_board
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
  Compatible:   example,board
                example,soc
  Loadables:    u-boot
                atf-2
"""


def test_parse_fit_selects_images_by_the_default_configuration() -> None:
    fit = parse_fit(KERNEL_FIT)
    assert (fit.selected("Kernel").index, fit.selected("FDT").index) == (0, 1)
    assert fit.selected("Kernel")["Compression"] == "lzma compressed"


def test_parse_fit_reads_list_properties() -> None:
    fit = parse_fit(UBOOT_FIT)
    assert fit.configuration.properties["Compatible"] == ["example,board", "example,soc"]
    assert fit.configuration.properties["Loadables"] == ["u-boot", "atf-2"]
    assert fit.selected("Firmware")["OS"] == "ARM Trusted Firmware"


def test_parse_fit_rejects_an_unavailable_image() -> None:
    with pytest.raises(LookupError, match="selects no Kernel image"):
        parse_fit(UBOOT_FIT).selected("Kernel")


def test_parse_fit_requires_a_default_configuration() -> None:
    with pytest.raises(LookupError, match="no default configuration"):
        parse_fit(KERNEL_FIT.replace(" Default Configuration: 'config-1'\n", ""))
