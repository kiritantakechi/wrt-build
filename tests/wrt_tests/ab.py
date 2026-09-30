"""The A/B slots as the tests see them (r4s-ab-rollback design D1, D4).

Everything goes through the router: the running slot from the kernel command
line, U-Boot variables through fw_printenv and fw_setenv, and checksums of disk
regions read with dd, so a test can tell which slot booted and what an upgrade
wrote without stopping the emulator.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wrt_tests.router import Router

# The emulator's boot disk, an SD card or an eMMC on its SD host controller.
BOOT_DISK = "/dev/mmcblk0"
# The U-Boot environment on the boot disk (design D1): offset and size in bytes.
ENV_OFFSET, ENV_SIZE = 0x3F8000, 0x8000
# The area U-Boot and the partition table occupy before boot-A, without the
# environment: MBR, loader (sector 64 on) and u-boot.itb (8 MiB on).
BOOT_AREA = ((0, 0x200), (0x8000, ENV_OFFSET), (0x800000, 0x2000000))
PARTITIONS = {"a": (1, 2), "b": (3, 4)}
READ_BLOCK = 1 << 20


def slot(router: Router) -> str:
    """Return the slot the router runs from, a or b."""
    arguments = router.run("cat /proc/cmdline").split()
    (running,) = [
        argument.removeprefix("wrt.slot=")
        for argument in arguments
        if argument.startswith("wrt.slot=")
    ]
    return running


def other(running: str) -> str:
    """Return the other slot."""
    return "b" if running == "a" else "a"


def getenv(router: Router, name: str) -> str | None:
    """Return a stored U-Boot variable, or None when it is not set."""
    code = router.returncode(f"fw_printenv -n {name} >/dev/null 2>&1")
    return router.run(f"fw_printenv -n {name}") if code == 0 else None


def setenv(router: Router, **variables: str | int) -> None:
    """Write U-Boot variables with the router's own helper, as wrt-slot and sysupgrade do."""
    pairs = " ".join(f"{name} {value}" for name, value in variables.items())
    router.run(f". /lib/functions/wrt-ab.sh && wrt_ab_setenv {pairs}")


def region_sha256(router: Router, device: str, start: int, end: int) -> str:
    """Return the SHA-256 of bytes ``start`` up to ``end`` of a block device.

    dd reads in the largest block (up to 1 MiB) both ends are a multiple of:
    a sector at a time, the emulated boot disk takes minutes for a slot.
    """
    block = READ_BLOCK
    while start % block or end % block:
        block //= 2
    return router.run(
        f"dd if={device} bs={block} skip={start // block} count={(end - start) // block}"
        " 2>/dev/null | sha256sum | cut -d' ' -f1",
        timeout=300,
    )


def partition(number: int) -> str:
    """Return the device of a partition of the boot disk."""
    return f"{BOOT_DISK}p{number}"


def erofs_size(router: Router, device: str) -> int:
    """Return the size of the EROFS image a partition starts with (superblock at 1 KiB)."""
    bits = int(
        router.run(f"dd if={device} bs=1 skip=1036 count=1 2>/dev/null | hexdump -e '1/1 \"%u\"'")
    )
    blocks = int(
        router.run(f"dd if={device} bs=4 skip=265 count=1 2>/dev/null | hexdump -e '1/4 \"%u\"'")
    )
    return blocks << bits


def slot_sha256(router: Router, which: str) -> dict[str, str]:
    """Checksums of what an upgrade must not touch in a slot: its boot partition and system."""
    boot, root = (partition(number) for number in PARTITIONS[which])
    size = int(router.run(f"cat /sys/class/block/{boot.removeprefix('/dev/')}/size")) * 512
    return {
        "boot": region_sha256(router, boot, 0, size),
        "system": region_sha256(router, root, 0, erofs_size(router, root)),
    }


def boot_area_sha256(router: Router) -> str:
    """Checksum of the partition table, loader and U-Boot, without the environment."""
    return ",".join(region_sha256(router, BOOT_DISK, start, end) for start, end in BOOT_AREA)
