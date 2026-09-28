"""testing/emulation: the emulator boots the shipped image as an R4S (design D14)."""

import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from wrt_tests import spec
from wrt_tests.emu import BOARD_COMPATIBLE, sha256

if TYPE_CHECKING:
    from wrt_tests.net import Network
    from wrt_tests.router import Router

CAPABILITY = "testing/emulation"
DHCP_TIMEOUT = 60.0


@spec(CAPABILITY, "Boot the shipped artifacts", "Verify artifact provenance")
def test_boots_the_shipped_artifacts(
    router: Router, emulation_dir: Path, emulation_source: dict[str, str]
) -> None:
    source = emulation_source
    image = Path(source["image"])
    manifest = json.loads(Path(source["manifest"]).read_text())
    assert sha256(image) == source["image_sha256"] == manifest["files"][f"targets/{image.name}"]

    kernel = emulation_dir / "Image"
    assert sha256(kernel) == source["kernel_sha256"]
    banner = re.search(rb"Linux version [^\n]+", kernel.read_bytes())
    assert banner is not None
    assert router.run("cat /proc/version") == banner.group().decode()

    assert "fstools_overlay_compression_type=zstd" in source["bootargs"].split()
    assert router.run("cat /proc/cmdline") == source["bootargs"]


@spec(CAPABILITY, "Boot with the R4S board identity", "Read board name")
def test_board_name(router: Router) -> None:
    assert router.run("cat /tmp/sysinfo/board_name") == BOARD_COMPATIBLE


@spec(CAPABILITY, "Instruction set matches the device", "Run userspace programs")
def test_userspace_runs(router: Router) -> None:
    # Programs built for cortex-a72.cortex-a53+crypto from several packages and
    # languages; an unsupported instruction would kill them with SIGILL.
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


@spec(CAPABILITY, "Repeatable network topology", "LAN client gets an address")
def test_lan_client_gets_an_address(router: Router, network: Network) -> None:
    client = network["client-a"]
    deadline = time.monotonic() + DHCP_TIMEOUT
    while not (address := client.run("ip", "-4", "-o", "addr", "show", "dev", "eth0").split()):
        assert time.monotonic() < deadline, "client-a got no DHCP lease"
        time.sleep(1)
    assert re.search(r"inet 10\.0\.0\.\d+/24", " ".join(address))
    client.run("ping", "-c", "1", "-W", "2", router.address)


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
