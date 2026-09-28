"""firmware/rootfs: an EROFS root with a zstd-compressed f2fs overlay behind it."""

import re
from http import HTTPStatus
from typing import TYPE_CHECKING

from wrt_tests import spec, target

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.router import Router

CAPABILITY = "firmware/rootfs"
# Digest of every file of the read-only root, independent of the overlay above it.
ROM_DIGEST = "find /rom -xdev -type f | sort | xargs sha256sum | sha256sum"


def _mount(router: Router, mountpoint: str) -> tuple[str, str, str]:
    """Return (source, type, options) of a mount point."""
    line = router.run(f"awk '$2 == \"{mountpoint}\"' /proc/mounts")
    source, _, kind, options, *_ = line.split()
    return source, kind, options


@spec(CAPABILITY, "EROFS root filesystem", "Check build artifacts")
@target("emulation", "reads the build outputs next to the emulated image")
def test_build_outputs_are_erofs(build_output: Path) -> None:
    images = sorted(p.name for p in (build_output / "targets").glob("*.img*"))
    assert images
    assert all("-erofs-" in name for name in images), images
    assert not [name for name in images if "squashfs" in name or "ext4" in name]


@spec(CAPABILITY, "EROFS root filesystem", "Check mounts on the router")
def test_rom_is_erofs(router: Router) -> None:
    _, kind, options = _mount(router, "/rom")
    assert kind == "erofs"
    assert options.split(",")[0] == "ro"


@spec(CAPABILITY, "Writable layer is zstd-compressed f2fs", "First boot creates the overlay")
def test_overlay_is_compressed_f2fs(router: Router) -> None:
    source, kind, options = _mount(router, "/overlay")
    assert kind == "f2fs"
    assert re.search(r"(^|,)compress_algorithm=zstd(:\d+)?(,|$)", options), options
    # The overlay is a loop device on the root partition itself, past the EROFS image.
    # fstools opens the partition during preinit, from a /dev that is mounted
    # elsewhere later, so the recorded path may lack the /dev prefix.
    loop = source.removeprefix("/dev/")
    backing = router.run(f"cat /sys/block/{loop}/loop/backing_file")
    assert re.fullmatch(r"(/dev)?/(vda|mmcblk\d+p)2", backing), backing
    assert int(router.run(f"cat /sys/block/{loop}/loop/offset")) > 0


@spec(CAPABILITY, "Factory reset clears only the writable layer", "Factory reset")
@target("emulation", "erases the router's configuration")
def test_factory_reset_only_clears_the_overlay(router: Router) -> None:
    rom = router.run(ROM_DIGEST)
    router.run("uci set system.@system[0].hostname=changed && uci commit system")
    router.run("touch /root/user-file && sync")
    router.reboot("firstboot -y && reboot")
    assert router.run("uci get system.@system[0].hostname") == "OpenWrt"
    assert router.returncode("[ -e /root/user-file ]") != 0
    assert router.run(ROM_DIGEST) == rom
    assert _mount(router, "/overlay")[1] == "f2fs"


@spec(CAPABILITY, "Image boots directly", "Boot after flashing")
@target("device", "the image has to be written to a microSD card in the R4S")
def test_flashed_image_boots(router: Router) -> None:
    router.wait_ready()
    status, page = router.http("/cgi-bin/luci/")
    assert status in {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
    assert "/luci-static/" in page
