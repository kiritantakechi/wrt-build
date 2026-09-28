"""firmware/ab-layout: four partitions, a factory image with both slots, an upgrade image of one."""

import gzip
import tarfile
from itertools import pairwise
from typing import TYPE_CHECKING

from wrt_tests import spec
from wrt_tests.ab import getenv, setenv, slot
from wrt_tests.image import SECTOR, read_mbr

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.router import Router

CAPABILITY = "firmware/ab-layout"
MIB = 1 << 20
# U-Boot and its environment end at 32 MiB; boot-A, root-A, boot-B, root-B follow.
RESERVED = 32 * MIB
PARTITION_SIZES = (64 * MIB, 1024 * MIB, 64 * MIB, 1024 * MIB)
# The smallest capacity a 4 GB microSD card offers.
CARD_4GB = 3_600_000_000


def _factory_disk(build_output: Path) -> bytes:
    """Read the MBR of the factory image."""
    (image,) = build_output.glob("targets/*-factory.img.gz")
    with gzip.open(image) as disk:
        return disk.read(SECTOR)


@spec(CAPABILITY, "Four-partition dual-slot layout", "Inspect the partition table")
def test_four_partitions(build_output: Path) -> None:
    partitions = read_mbr(_factory_disk(build_output)).partitions
    assert [p.number for p in partitions] == [1, 2, 3, 4]
    assert [p.size for p in partitions] == list(PARTITION_SIZES)
    assert partitions[0].start == RESERVED
    assert all(a.start + a.size <= b.start for a, b in pairwise(partitions))


@spec(CAPABILITY, "Factory image", "First boot")
def test_first_boot_takes_slot_a(router: Router) -> None:
    assert slot(router) == "a"
    assert getenv(router, "boot_slot") is None


@spec(CAPABILITY, "Factory image", "Slot B also boots")
def test_slot_b_boots(router: Router) -> None:
    setenv(router, boot_slot="b")
    router.reboot()
    assert slot(router) == "b"
    assert router.run("awk '$2 == \"/overlay\" { print $3 }' /proc/mounts") == "f2fs"


@spec(CAPABILITY, "Single-slot upgrade image", "Inspect upgrade image contents")
def test_upgrade_image_holds_one_slot(upgrade_image: Path) -> None:
    # gzip stops at the end of its stream; the fwtool metadata after it is ignored.
    with gzip.open(upgrade_image) as stream, tarfile.open(fileobj=stream, mode="r|") as archive:
        members = {member.name.split("/", 1)[-1] for member in archive if member.isfile()}
    assert members == {"CONTROL", "kernel", "root"}


@spec(CAPABILITY, "Fits a 4 GB SD card", "Write to a 4 GB card")
def test_factory_image_fits_a_4gb_card(router: Router, build_output: Path) -> None:
    partitions = read_mbr(_factory_disk(build_output)).partitions
    assert partitions[-1].start + partitions[-1].size <= CARD_4GB
    # The emulator's card is this image (both slots booting from it: "Slot B also boots").
    assert slot(router) == "a"
