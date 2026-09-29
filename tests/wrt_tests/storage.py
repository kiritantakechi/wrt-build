"""The USB data disk in the emulator (r4s-services D1, D10).

A disk is a sparse raw image on the runner that the tests plug into the
emulator's xHCI controller as a UAS device. The router shows its SCSI product
name as the disk's model, which is how the tests find its block device.
``initialize`` runs ``wrt-data init`` as an administrator would: the device, then
its name typed again to confirm.
"""

import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from wrt_tests.poll import until

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.emu import Emulator
    from wrt_tests.router import Router

MOUNT = "/mnt/data"
SUBVOLUMES = ("containers", "downloads", "shares", "logs")
# Sparse: only what the router writes takes space on the runner.
SIZE = 8 << 30
PLUG_TIMEOUT = 60
INIT_TIMEOUT = 120


@dataclass
class Disk:
    """A USB SSD of the emulator: a sparse image, plugged in on a port or not."""

    emulator: Emulator
    name: str
    image: Path
    port: int | None = None

    @classmethod
    def blank(cls, emulator: Emulator, directory: Path, name: str) -> Self:
        """Create a blank disk named ``name`` (at most 16 characters: a SCSI product)."""
        image = directory / f"{name}.raw"
        with image.open("xb") as file:
            file.truncate(SIZE)
        return cls(emulator, name, image)

    def plug(self, port: int) -> None:
        """Plug the disk in on xHCI port ``port``."""
        self.emulator.plug_disk(self.name, self.image, port)
        self.port = port

    def unplug(self) -> None:
        """Pull the disk out, if it is plugged in."""
        if self.port is not None:
            self.emulator.unplug_disk(self.name)
            self.port = None

    @property
    def blank_still(self) -> bool:
        """Whether nothing was ever written to the disk: its image has no blocks yet."""
        return self.image.stat().st_blocks == 0


def device(router: Router, disk: Disk) -> str:
    """Wait for ``disk``'s block device on the router and return its path."""
    # The SCSI model is padded with spaces.
    command = f"grep -l {shlex.quote(f'^{disk.name} *$')} /sys/block/sd*/device/model || true"
    model = until(
        lambda: router.run(command) or None,
        timeout=PLUG_TIMEOUT,
        what=f"{disk.name}'s block device",
    )
    return f"/dev/{model.split('/')[3]}"


def mount_options(router: Router) -> set[str] | None:
    """Return the options of the data disk's mount, or None while it is not mounted."""
    options = router.run(f'awk \'$2 == "{MOUNT}" && $3 == "btrfs" {{ print $4 }}\' /proc/mounts')
    return set(options.split(",")) if options else None


def wait_mounted(router: Router) -> set[str]:
    """Wait until the data disk is mounted; return its mount options."""
    return until(lambda: mount_options(router), timeout=PLUG_TIMEOUT, what=f"{MOUNT} mounted")


def initialize(router: Router, disk: Disk, answer: str | None = None) -> int:
    """Run ``wrt-data init`` on ``disk``, answering its question; return its exit status.

    The answer is the device's own name unless ``answer`` says otherwise.
    """
    path = device(router, disk)
    typed = shlex.quote(path if answer is None else answer)
    return router.returncode(f"echo {typed} | wrt-data init {path}", timeout=INIT_TIMEOUT)


def subvolumes(router: Router) -> set[str]:
    """Return the paths of the subvolumes on the data disk, relative to its top level."""
    listing = router.run(f"btrfs subvolume list {MOUNT}")
    return {line.split(" path ", 1)[1] for line in listing.splitlines()}
