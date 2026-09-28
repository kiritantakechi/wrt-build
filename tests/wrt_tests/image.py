"""Read the pieces of a shipped sysupgrade image that the emulator boots (design D14).

Everything here is a pure function over bytes, so the unit tests cover it without
an image: the gzip stream is followed by fwtool metadata, the disk has an MBR, and
the boot partition holds a legacy U-Boot script whose ``setenv bootargs`` line is
the template of the kernel command line.
"""

import re
import struct
import zlib
from dataclasses import dataclass
from typing import BinaryIO

SECTOR = 512
_MBR_SIGNATURE = 0x1B8
_MBR_ENTRIES = 0x1BE
_MBR_ENTRY_SIZE = 16
_LEGACY_HEADER_SIZE = 64
_BOOTARGS = re.compile(r'setenv bootargs "(?P<template>[^"]*)"')


@dataclass(frozen=True, slots=True)
class Partition:
    """One primary MBR partition, numbered from 1."""

    number: int
    start: int
    size: int

    def read(self, disk: bytes) -> bytes:
        """Return the bytes of this partition."""
        return disk[self.start : self.start + self.size]


@dataclass(frozen=True, slots=True)
class Disk:
    """The partition table of a disk image."""

    signature: int
    partitions: tuple[Partition, ...]

    def partuuid(self, number: int) -> str:
        """Linux PARTUUID of a partition on an MBR disk: ``<signature>-<number>``."""
        return f"{self.signature:08x}-{number:02x}"

    def partition(self, number: int) -> Partition:
        """Return the partition with this number."""
        for partition in self.partitions:
            if partition.number == number:
                return partition
        msg = f"no partition {number}"
        raise LookupError(msg)


def gunzip_first_member(source: BinaryIO, target: BinaryIO, chunk: int = 1 << 20) -> bytes:
    """Stream the first gzip member of ``source`` into ``target``; return what follows it.

    sysupgrade images carry fwtool metadata after the gzip stream, which gzip(1)
    reports as trailing garbage.
    """
    decompressor = zlib.decompressobj(zlib.MAX_WBITS | 16)
    while not decompressor.eof and (block := source.read(chunk)):
        target.write(decompressor.decompress(block))
    if not decompressor.eof:
        msg = "truncated gzip stream"
        raise ValueError(msg)
    target.write(decompressor.flush())
    return decompressor.unused_data + source.read()


def read_mbr(disk: bytes) -> Disk:
    """Parse the MBR: disk signature and the non-empty primary partitions."""
    if disk[510:512] != b"\x55\xaa":
        msg = "no MBR boot signature"
        raise ValueError(msg)
    (signature,) = struct.unpack_from("<I", disk, _MBR_SIGNATURE)
    partitions = []
    for index in range(4):
        start, sectors = struct.unpack_from("<II", disk, _MBR_ENTRIES + index * _MBR_ENTRY_SIZE + 8)
        if sectors:
            partitions.append(Partition(index + 1, start * SECTOR, sectors * SECTOR))
    return Disk(signature, tuple(partitions))


def script_text(script: bytes) -> str:
    """Return the text of a legacy U-Boot script image (mkimage -T script).

    After the 64-byte legacy header comes a zero-terminated table of big-endian
    part lengths; the first part is the script.
    """
    offset = _LEGACY_HEADER_SIZE
    lengths: list[int] = []
    while (length := struct.unpack_from(">I", script, offset)[0]) != 0:
        lengths.append(length)
        offset += 4
    offset += 4
    if not lengths:
        msg = "empty script image"
        raise ValueError(msg)
    return script[offset : offset + lengths[0]].decode()


def emulator_bootargs(script: str, partuuid: str, console: str = "ttyAMA0") -> str:
    """Turn the ``setenv bootargs`` template of the boot script into emulator bootargs.

    The console moves to the emulator's PL011 UART, earlycon (the RK3399 UART
    address) is dropped and the root partition is named by PARTUUID, exactly as
    the script's ``part uuid`` does on the device. Every other argument is kept.
    """
    match = _BOOTARGS.search(script)
    if match is None:
        msg = "boot script sets no bootargs"
        raise ValueError(msg)
    arguments: list[str] = []
    for argument in match["template"].split():
        if argument.startswith("earlycon="):
            continue
        if argument.startswith("console="):
            arguments.append(f"console={console}")
        else:
            arguments.append(argument.replace("${uuid}", partuuid))
    return " ".join(arguments)


_FIT_IMAGE = re.compile(r"^ Image (?P<index>\d+) \(")
_FIT_KERNEL = re.compile(r"^\s+Type:\s+Kernel Image\s*$")


def fit_kernel_index(listing: str) -> int:
    """Return the index of the kernel image in a ``dumpimage -l`` listing of a FIT."""
    index: int | None = None
    for line in listing.splitlines():
        if image := _FIT_IMAGE.match(line):
            index = int(image["index"])
        elif _FIT_KERNEL.match(line) and index is not None:
            return index
    msg = "the FIT holds no kernel image"
    raise LookupError(msg)
