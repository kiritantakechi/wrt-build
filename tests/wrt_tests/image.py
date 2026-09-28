"""Read the pieces of a shipped sysupgrade image (design D14).

Everything here is a pure function over bytes or text, so the unit tests cover it
without an image: the gzip stream is followed by fwtool metadata, the disk has an
MBR, the boot partition holds a legacy U-Boot script whose ``setenv bootargs`` line
is the template of the kernel command line, and U-Boot and the kernel are FITs,
read from their ``dumpimage -l`` listings.
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


_FIT_NODE = re.compile(r"^ (?P<kind>Image|Configuration) (?P<index>\d+) \((?P<name>[^)]+)\)$")
_FIT_DEFAULT = re.compile(r"^ Default Configuration: '(?P<name>[^']+)'$")
_FIT_PROPERTY = re.compile(r"^  (?P<key>\S[^:]*):\s+(?P<value>.*?)\s*$")
_FIT_CONTINUATION = re.compile(r"^ {3,}(?P<value>\S.*?)\s*$")


@dataclass(frozen=True, slots=True)
class FitNode:
    """One image or configuration of a FIT, with its listed properties."""

    index: int
    name: str
    properties: dict[str, list[str]]

    def __getitem__(self, key: str) -> str:
        """Return the first value of a property; lists (Compatible, Loadables) have more."""
        return self.properties[key][0]


@dataclass(frozen=True, slots=True)
class Fit:
    """The images and configurations of a FIT, keyed by name."""

    images: dict[str, FitNode]
    configurations: dict[str, FitNode]
    default: str

    @property
    def configuration(self) -> FitNode:
        """Return the default configuration, the one bootm and SPL boot."""
        return self.configurations[self.default]

    def selected(self, key: str) -> FitNode:
        """Return the image the default configuration selects as ``key`` (Kernel, FDT, ...)."""
        name = self.configuration.properties.get(key, [""])[0]
        if name not in self.images:
            msg = f"configuration {self.default} selects no {key} image"
            raise LookupError(msg)
        return self.images[name]


def parse_fit(listing: str) -> Fit:
    """Parse a ``dumpimage -l`` listing of a FIT.

    Nodes start at one space of indent, their properties at two, and the further
    values of a list property (Compatible, Loadables) are indented deeper still.
    """
    nodes: dict[str, dict[str, FitNode]] = {"Image": {}, "Configuration": {}}
    default: str | None = None
    node: FitNode | None = None
    values: list[str] = []
    for line in listing.splitlines():
        if match := _FIT_NODE.match(line):
            node = FitNode(int(match["index"]), match["name"], {})
            nodes[match["kind"]][node.name] = node
        elif match := _FIT_DEFAULT.match(line):
            default, node = str(match["name"]), None
        elif node is not None and (match := _FIT_PROPERTY.match(line)):
            values = node.properties[match["key"]] = [match["value"]]
        elif node is not None and (match := _FIT_CONTINUATION.match(line)):
            values.append(match["value"])
    if default is None:
        msg = "the FIT has no default configuration"
        raise LookupError(msg)
    return Fit(nodes["Image"], nodes["Configuration"], default)
