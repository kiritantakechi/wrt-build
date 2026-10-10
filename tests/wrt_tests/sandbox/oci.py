"""A container image made of the shipped firmware's own programs (r4s-services D10).

The tests' app container serves HTTP with uhttpd and makes requests with
busybox's nc and uclient-fetch, as the firmware's busybox has neither httpd nor
wget. Its image comes from slot A's root filesystem of the factory disk, so it
is arm64 like the router and needs no download: one layer with busybox and its
applet links, uhttpd, uclient-fetch and the shared libraries they need, in an
OCI image layout that skopeo copies to the emulated internet's registry.
"""

import gzip
import hashlib
import io
import json
import struct
import subprocess
import tarfile
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from wrt_tests.model.image import SECTOR, read_mbr

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.sandbox.net import Netns

IMAGE = "wrt/app"
TAG = "1"
ROOT_PARTITION = 2  # slot A's root: EROFS, then the overlay area
APPLETS = ("sh", "cat", "echo", "ls", "mkdir", "nc", "sleep", "true")
PROGRAMS = ("bin/busybox", "usr/sbin/uhttpd", "bin/uclient-fetch")
LIBRARY_DIRECTORIES = ("lib", "usr/lib")
# musl's dynamic loader is its libc.
LOADER = ("lib/ld-musl-aarch64.so.1", "libc.so")
MEDIA = "application/vnd.oci.image"
# struct erofs_super_block at byte 1024: magic, then blkszbits at 12, blocks at 36.
EROFS_SUPERBLOCK = 1024
EROFS_FIELDS = struct.Struct("<I8xB23xI")
EROFS_MAGIC = 0xE0F5E1E2
# 64-bit little-endian ELF: the header up to e_phnum, program headers, dynamic entries.
ELF_HEADER = struct.Struct("<4sB27xQ16xH")
PROGRAM_HEADER = struct.Struct("<I4xQQ8xQ16x")
DYNAMIC_ENTRY = struct.Struct("<qQ")
PT_LOAD, PT_DYNAMIC = 1, 2
DT_NULL, DT_NEEDED, DT_STRTAB = 0, 1, 5


def extract_root(disk: Path, output: Path) -> Path:
    """Extract slot A's root filesystem of a factory disk image into ``output``.

    Only the EROFS image is copied out: its superblock gives its size, and the
    rest of the partition is the overlay area.
    """
    image = output.with_suffix(".erofs")
    with disk.open("rb") as raw, image.open("wb") as erofs:
        root = read_mbr(raw.read(SECTOR)).partition(ROOT_PARTITION)
        raw.seek(root.start + EROFS_SUPERBLOCK)
        magic, block_bits, blocks = EROFS_FIELDS.unpack(raw.read(EROFS_FIELDS.size))
        if magic != EROFS_MAGIC:
            msg = f"partition {ROOT_PARTITION} of {disk} holds no EROFS image"
            raise ValueError(msg)
        raw.seek(root.start)
        remaining = blocks << block_bits
        while remaining:
            chunk = raw.read(min(remaining, 1 << 20))
            erofs.write(chunk)
            remaining -= len(chunk)
    subprocess.run(["fsck.erofs", f"--extract={output}", image], check=True, capture_output=True)
    image.unlink()
    return output


def needed(elf: bytes) -> list[str]:
    """Return the shared libraries an arm64 ELF file needs (its DT_NEEDED entries)."""
    magic, elf_class, program_headers, count = ELF_HEADER.unpack_from(elf)
    if (magic, elf_class) != (b"\x7fELF", 2):
        msg = "not a 64-bit ELF file"
        raise ValueError(msg)
    segments = [
        PROGRAM_HEADER.unpack_from(elf, program_headers + index * PROGRAM_HEADER.size)
        for index in range(count)
    ]

    def offset(address: int) -> int:
        for kind, file_offset, virtual, size in segments:
            if kind == PT_LOAD and virtual <= address < virtual + size:
                return int(file_offset + address - virtual)
        msg = f"address {address:#x} is in no loaded segment"
        raise ValueError(msg)

    dynamic = [segment for segment in segments if segment[0] == PT_DYNAMIC]
    if not dynamic:
        return []  # static
    entries = []
    _, start, _, size = dynamic[0]
    for position in range(start, start + size, DYNAMIC_ENTRY.size):
        tag, value = DYNAMIC_ENTRY.unpack_from(elf, position)
        if tag == DT_NULL:
            break
        entries.append((tag, value))
    strings = offset(next(value for tag, value in entries if tag == DT_STRTAB))
    return [
        elf[strings + value : elf.index(b"\0", strings + value)].decode()
        for tag, value in entries
        if tag == DT_NEEDED
    ]


def _files(root: Path) -> dict[str, bytes]:
    """Return the programs and, transitively, the libraries they need, by path in the image."""
    files: dict[str, bytes] = {}
    pending = list(PROGRAMS)
    while pending:
        name = pending.pop()
        if name in files:
            continue
        files[name] = (root / name).read_bytes()  # a library's link, as the file it names
        for library in needed(files[name]):
            found = [f"{d}/{library}" for d in LIBRARY_DIRECTORIES if (root / d / library).exists()]
            if not found:
                msg = f"{library}, which {name} needs, is not in {root}"
                raise FileNotFoundError(msg)
            pending.append(found[0])
    return files


def _layer(root: Path) -> bytes:
    """Return the layer as an uncompressed, reproducible tar."""
    files = _files(root)
    links = {LOADER[0]: LOADER[1], **{f"bin/{applet}": "busybox" for applet in APPLETS}}
    directories = sorted(
        {"www"}
        | {str(parent) for name in [*files, *links] for parent in PurePosixPath(name).parents}
        - {"."}
    )
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for directory in directories:
            info = tarfile.TarInfo(directory)
            info.type, info.mode = tarfile.DIRTYPE, 0o755
            tar.addfile(info)
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.mode, info.size = 0o755, len(data)
            tar.addfile(info, io.BytesIO(data))
        for name, target in sorted(links.items()):
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, target
            tar.addfile(info)
    return buffer.getvalue()


def _blob(layout: Path, data: bytes, media_type: str) -> dict[str, object]:
    digest = hashlib.sha256(data).hexdigest()
    (layout / "blobs" / "sha256" / digest).write_bytes(data)
    return {"mediaType": media_type, "digest": f"sha256:{digest}", "size": len(data)}


def _json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def image_layout(root: Path, layout: Path, tag: str = TAG) -> Path:
    """Write an OCI image layout of the programs in ``root`` into ``layout``."""
    (layout / "blobs" / "sha256").mkdir(parents=True)
    tar = _layer(root)
    layer = _blob(layout, gzip.compress(tar, mtime=0), f"{MEDIA}.layer.v1.tar+gzip")
    config = _blob(
        layout,
        _json(
            {
                "architecture": "arm64",
                "os": "linux",
                "config": {"Cmd": ["/bin/sh"]},
                "rootfs": {
                    "type": "layers",
                    "diff_ids": [f"sha256:{hashlib.sha256(tar).hexdigest()}"],
                },
            }
        ),
        f"{MEDIA}.config.v1+json",
    )
    manifest = _blob(
        layout,
        _json(
            {
                "schemaVersion": 2,
                "mediaType": f"{MEDIA}.manifest.v1+json",
                "config": config,
                "layers": [layer],
            }
        ),
        f"{MEDIA}.manifest.v1+json",
    )
    manifest["annotations"] = {"org.opencontainers.image.ref.name": tag}
    (layout / "index.json").write_bytes(_json({"schemaVersion": 2, "manifests": [manifest]}))
    (layout / "oci-layout").write_bytes(_json({"imageLayoutVersion": "1.0.0"}))
    return layout


def push(netns: Netns, layout: Path, tag: str, reference: str, workdir: Path) -> None:
    """Copy the image ``tag`` of ``layout`` to the registry as ``reference``, from ``netns``.

    ``workdir`` is the sandbox's: its test CA and the signature policy.
    """
    netns.run(
        *("skopeo", f"--policy={workdir / 'inet' / 'policy.json'}", "copy", "--quiet"),
        f"--dest-cert-dir={workdir / 'pki' / 'trust'}",
        *(f"oci:{layout}:{tag}", f"docker://{reference}"),
        timeout=300,
    )
