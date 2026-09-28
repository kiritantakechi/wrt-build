"""Unit tests of wrt_tests.image: reading a sysupgrade image without a device."""

import gzip
import io
import struct

import pytest

from wrt_tests.image import (
    SECTOR,
    emulator_bootargs,
    fit_kernel_index,
    gunzip_first_member,
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


FIT_LISTING = """FIT description: ARM64 OpenWrt FIT (Flattened Image Tree)
 Image 0 (fdt-1)
  Type:         Flat Device Tree
 Image 1 (kernel-1)
  Description:  ARM64 OpenWrt Linux-6.18.52
  Type:         Kernel Image
  Compression:  lzma compressed
 Default Configuration: 'config-1'
"""


def test_fit_kernel_index_finds_the_kernel_image() -> None:
    assert fit_kernel_index(FIT_LISTING) == 1


def test_fit_kernel_index_rejects_a_fit_without_kernel() -> None:
    with pytest.raises(LookupError, match="no kernel"):
        fit_kernel_index(FIT_LISTING.replace("Kernel Image", "Ramdisk Image"))
