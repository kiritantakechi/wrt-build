"""Unit tests of wrt_tests.emu: the machine that stands in for each board (board-model D7)."""

import shlex
from typing import TYPE_CHECKING, Any

import pytest

from wrt_tests.boards import Board, load_all
from wrt_tests.emu import BOOT_DISKS, Machine
from wrt_tests.net import segments, taps

if TYPE_CHECKING:
    from pathlib import Path


def _options(driver: dict[str, Any], name: str) -> list[dict[str, str]]:
    """Return the values of a QEMU option in the driver's arguments, as key=value maps.

    A value's first item, a device or backend type, is under ``type``.
    """
    arguments = shlex.split(driver["extra_args"])
    return [
        {"type": kind, **dict(item.split("=", 1) for item in items)}
        for option, value in zip(arguments[::2], arguments[1::2], strict=True)
        if option == name
        for kind, *items in [value.split(",")]
    ]


@pytest.mark.parametrize("board", load_all(), ids=lambda board: board.id)
def test_the_machine_follows_the_board(board: Board, tmp_path: Path) -> None:
    description = Machine(board).description(tmp_path)
    driver = description["targets"]["main"]["drivers"]["QEMUDriver"]
    assert (driver["cpu"], driver["memory"]) == (board.emulator.cpu, board.emulator.memory)
    assert _options(driver, "-smp") == [{"type": str(len(board.soc.cores))}]
    devices = _options(driver, "-device")
    assert BOOT_DISKS[board.boot_disk].device in [device["type"] for device in devices]
    # One NIC per port, in the board's order, each on its segment's tap.
    netdevs = _options(driver, "-netdev")
    assert [(netdev["id"], netdev["ifname"]) for netdev in netdevs] == list(
        zip(segments(board), taps(board), strict=True)
    )
    nics = [device for device in devices if device["type"] == "virtio-net-pci"]
    assert [nic["netdev"] for nic in nics] == list(segments(board))
    assert len({nic["mac"] for nic in nics}) == len(board.ports)
    assert description["images"] == {
        "bios": str(tmp_path / "u-boot.bin"),
        "dtb": str(tmp_path / "board.dtb"),
    }
