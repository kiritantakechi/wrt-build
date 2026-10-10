"""The build's and the release's outputs as data (module-boundaries D7).

``scripts/build.sh`` writes a build's ``manifest.json``; a release carries it as
``<device>-manifest.json``, and a drill base carries the manifest of the build
its image comes from. ``emu-prepare`` records what an emulator directory was
made from (``source.json``), ``scripts/toolchain-build.sh`` what a toolchain was
built with (``wrt-toolchain.json``), and ``scripts/release-publish.sh`` what a
release is (``release.json``). Each is read through its model here, strict
about unknown fields and types (``wrt_tests.model.data``).
"""

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer
from pydantic_core import PydanticCustomError

MANIFEST_FILE = "manifest.json"
SOURCE_FILE = "source.json"
TOOLCHAIN_FILE = "wrt-toolchain.json"
RELEASE_FILE = "release.json"

type Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _split(flags: object) -> object:
    """Split the compiler flags the scripts write as one string, as the compiler reads them."""
    if not isinstance(flags, str):
        kind, msg = "string_type", "compiler flags are one string"
        raise PydanticCustomError(kind, msg)
    return tuple(flags.split())


type Flags = Annotated[
    tuple[str, ...], BeforeValidator(_split), PlainSerializer(" ".join, return_type=str)
]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Manifest(_Record):
    """A build's manifest: which board was built, from what, with which flags, and its files."""

    board: str
    device: str
    run: str
    profile: str
    build: str
    cflags: Flags
    kernel_cflags: Flags
    toolchain_cflags: Flags
    upstream_lock_sha256: Sha256
    patches_sha256: Sha256
    openwrt_head: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    kernel_version: str
    vermagic: str
    files: dict[str, Sha256]


class EmulationSource(_Record):
    """What an emulator directory was made from: a build's factory image and firmware."""

    build: Path
    board: str
    image: Path
    image_sha256: Sha256
    firmware: Path
    firmware_sha256: Sha256


class ToolchainRecord(_Record):
    """What a toolchain was built with: the flags, its C library, and Rust's standard library.

    ``rust_std`` is absent until the toolchain has built Rust's.
    """

    cflags: Flags
    libc: Sha256
    rust_std: Sha256 | None = None


class Release(_Record):
    """A release: its tag, whether it is a candidate, its notes, boards and assets."""

    tag: Annotated[str, Field(min_length=1)]
    prerelease: bool
    notes: str
    boards: tuple[str, ...]
    assets: tuple[str, ...]
