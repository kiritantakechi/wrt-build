"""testing/emulation: the emulator boots the shipped image as its board (D14, board-model D7)."""

import ipaddress
import json
import lzma
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.emu import MANIFEST_FILE, boot_files, extract_fit_image, read_fit, sha256
from wrt_tests.poll import until
from wrt_tests.storage import PLUG_TIMEOUT, Disk, device

if TYPE_CHECKING:
    from wrt_tests.boards import Board
    from wrt_tests.net import Netns, Network
    from wrt_tests.router import Router

CAPABILITY = "testing/emulation"
DHCP_TIMEOUT = 60.0
LAN = ipaddress.ip_network("10.0.0.0/24")


@spec(CAPABILITY, "Boot the shipped artifacts", "Verify artifact provenance")
def test_boots_the_shipped_artifacts(
    router: Router,
    emulation_dir: Path,
    emulation_source: dict[str, str],
    build_output: Path,
    tmp_path: Path,
) -> None:
    files = json.loads((build_output / MANIFEST_FILE).read_text())["files"]
    for kind in ("image", "firmware"):
        path = Path(emulation_source[kind])
        shipped = files[path.relative_to(build_output).as_posix()]
        assert sha256(path) == emulation_source[f"{kind}_sha256"] == shipped

    # U-Boot started the kernel of slot A's FIT, with the slot's command line.
    boot_files(emulation_dir / "disk.raw", 1, ("kernel.img",), tmp_path)
    kernel = tmp_path / "kernel.img"
    extract_fit_image(kernel, read_fit(kernel).selected("Kernel"), tmp_path / "Image.lzma")
    image = lzma.decompress((tmp_path / "Image.lzma").read_bytes())
    banner = re.search(rb"Linux version [^\n]+", image)
    assert banner is not None
    assert router.run("cat /proc/version") == banner.group().decode()
    arguments = router.run("cat /proc/cmdline").split()
    assert {"wrt.slot=a", "fstools_overlay_compression_type=zstd"} <= set(arguments)


@spec(CAPABILITY, "Boot with the board identity", "Read board name")
def test_board_name(router: Router, board: Board) -> None:
    assert router.run("cat /tmp/sysinfo/board_name") == board.board_name


@spec(CAPABILITY, "Instruction set matches the device", "Run userspace programs")
def test_userspace_runs(router: Router) -> None:
    # Programs built for the board's CPU from several packages and languages;
    # an unsupported instruction would kill them with SIGILL.
    for program in (
        "busybox true",
        "ubus call system board",
        "uci show system",
        "apk --version",
        "bash -c true",
        "zsh -fc true",
        "ucode -e 'print(1)'",
        "dropbearkey -t ed25519 -f /tmp/emulation-test.key",
    ):
        assert router.returncode(f"{program} >/dev/null") == 0, program
    assert router.returncode("dmesg | grep -qi 'illegal instruction\\|undefined instruction'") != 0


@spec(CAPABILITY, "The board's cores", "Read core capacities")
def test_the_cores_are_the_board_s(router: Router, board: Board) -> None:
    # The kernel scales the device tree's capacities so that the highest is 1024.
    listing = router.run("grep -H . /sys/devices/system/cpu/cpu[0-9]*/cpu_capacity")
    reported = {
        int(cpu): int(capacity)
        for cpu, capacity in re.findall(r"/cpu(\d+)/cpu_capacity:(\d+)", listing)
    }
    highest = max(board.soc.cores)
    scaled = {cpu: capacity * 1024 // highest for cpu, capacity in enumerate(board.soc.cores)}
    assert reported == scaled


def _lease(client: Netns) -> str:
    """Wait for the client's DHCP lease; return its address, which must be in the LAN."""
    shown = until(
        lambda: client.run("ip", "-4", "-o", "addr", "show", "dev", "eth0") or None,
        timeout=DHCP_TIMEOUT,
        what=f"DHCP lease of {client.name}",
    )
    lease = ipaddress.ip_interface(shown.split()[3])
    assert lease.network == LAN, shown
    return str(lease.ip)


@spec(CAPABILITY, "Repeatable network topology", "LAN client gets an address")
def test_lan_client_gets_an_address(router: Router, network: Network) -> None:
    _lease(network["client-a"])
    network["client-a"].run("ping", "-c", "1", "-W", "2", router.address)


@spec(CAPABILITY, "Repeatable network topology", "Clients on both LAN ports share one LAN")
def test_lan_ports_share_one_lan(router: Router, board: Board, network: Network) -> None:
    del router  # requested for the booted router, whose LAN bridges the ports
    if len(board.lan) < 2:  # noqa: PLR2004
        pytest.skip(f"the {board.model} has one LAN port")
    # client-a is on the first LAN port's segment, client-c on the second's.
    address = _lease(network["client-a"])
    _lease(network["client-c"])
    network["client-c"].run("ping", "-c", "1", "-W", "2", address)


@spec(CAPABILITY, "Repeatable network topology", "No root privileges needed")
def test_sandbox_needs_no_root(router: Router, network: Network) -> None:
    # Root in here is the invoking user outside: uid_map is "0 <uid> 1".
    inside, outside, count = map(int, Path("/proc/self/uid_map").read_text().split())
    assert (inside, count) == (0, 1)
    assert outside != 0
    assert network["client-a"].run("true") == ""
    assert router.run("true") == ""


@spec(CAPABILITY, "Fault injection", "Tests are isolated")
def test_tests_do_not_leak_state(router: Router) -> None:
    router.run("uci set system.@system[0].hostname=leaked && uci commit system && sync")
    router.reset()  # what the router fixture does between two tests
    assert router.run("uci get system.@system[0].hostname") == "OpenWrt"


@spec(CAPABILITY, "Fault injection", "Forced power cut")
def test_power_cut_keeps_the_disk(router: Router) -> None:
    emulator = router.emulator
    router.run("echo written-before-the-cut > /root/marker && sync")
    router.disconnect()
    emulator.power_cut()
    emulator.power_on()
    router.wait_ready()
    assert router.run("cat /root/marker") == "written-before-the-cut"


@spec(CAPABILITY, "USB storage", "Hot-plug a USB disk")
def test_usb_disk_hot_plug(router: Router, tmp_path: Path) -> None:
    # The xHCI controller's two root hubs, USB 2 and USB 3.
    hubs = router.run("cat /sys/bus/usb/devices/usb*/product").splitlines()
    assert hubs == ["xHCI Host Controller"] * 2
    disk = Disk.blank(router.emulator, tmp_path, "hotplug")
    disk.plug(4)
    try:
        path = device(router, disk)
        name = path.removeprefix("/dev/")
        # Bound to uas, as the boards' data disks, at SuperSpeed: the SCSI device's USB
        # interface is three levels up, the USB device four.
        usb = f"/sys/block/{name}/device/../../.."
        assert router.run(f"readlink -f {usb}/driver").endswith("/uas")
        assert router.run(f"cat {usb}/../speed") == "5000"
    finally:
        disk.unplug()
    until(
        lambda: router.returncode(f"test -e /sys/block/{name}") != 0,
        timeout=PLUG_TIMEOUT,
        what=f"{path} gone",
    )
