"""testing/emulation: the emulator boots the shipped image as an R4S (design D14)."""

import json
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from wrt_tests import spec, target
from wrt_tests.emu import BOARD_COMPATIBLE, sha256

if TYPE_CHECKING:
    from wrt_tests.net import Network
    from wrt_tests.router import Router

CAPABILITY = "testing/emulation"
DHCP_TIMEOUT = 60.0


@spec(CAPABILITY, "启动的是出货产物", "核对产物来源")
@target("emulation", "checks where the emulator's kernel and disk come from")
def test_boots_the_shipped_artifacts(router: Router, emulation_source: dict[str, str]) -> None:
    source = emulation_source
    image = Path(source["image"])
    manifest = json.loads(Path(source["manifest"]).read_text())
    assert sha256(image) == source["image_sha256"] == manifest["files"][f"targets/{image.name}"]

    kernel = Path(os.environ["LG_EMU_DIR"]) / "Image"
    assert sha256(kernel) == source["kernel_sha256"]
    banner = re.search(rb"Linux version [^\n]+", kernel.read_bytes())
    assert banner is not None
    assert router.run("cat /proc/version") == banner.group().decode()

    assert "fstools_overlay_compression_type=zstd" in source["bootargs"].split()
    assert router.run("cat /proc/cmdline") == source["bootargs"]


@spec(CAPABILITY, "以 R4S 的板型身份启动", "读取板型")
def test_board_name(router: Router) -> None:
    assert router.run("cat /tmp/sysinfo/board_name") == BOARD_COMPATIBLE


@spec(CAPABILITY, "指令集与真机一致", "运行用户态程序")
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


@spec(CAPABILITY, "可重复的网络拓扑", "局域网客户端获得地址")
@target("emulation", "the LAN client lives in the emulator's network sandbox")
def test_lan_client_gets_an_address(router: Router, network: Network) -> None:
    client = network["client-a"]
    deadline = time.monotonic() + DHCP_TIMEOUT
    while not (address := client.run("ip", "-4", "-o", "addr", "show", "dev", "eth0").split()):
        assert time.monotonic() < deadline, "client-a got no DHCP lease"
        time.sleep(1)
    assert re.search(r"inet 10\.0\.0\.\d+/24", " ".join(address))
    client.run("ping", "-c", "1", "-W", "2", router.address)


@spec(CAPABILITY, "可重复的网络拓扑", "不需要 root 权限")
@target("emulation", "concerns how the emulator's sandbox is built")
def test_sandbox_needs_no_root(router: Router, network: Network) -> None:
    # Root in here is the invoking user outside: uid_map is "0 <uid> 1".
    inside, outside, count = map(int, Path("/proc/self/uid_map").read_text().split())
    assert (inside, count) == (0, 1)
    assert outside != 0
    assert network["client-a"].run("true") == ""
    assert router.run("true") == ""


@spec(CAPABILITY, "故障注入", "用例之间互不影响")
@target("emulation", "the device keeps its state between tests")
def test_tests_do_not_leak_state(router: Router) -> None:
    router.run("uci set system.@system[0].hostname=leaked && uci commit system && sync")
    router.reset()  # what the router fixture does between two tests
    assert router.run("uci get system.@system[0].hostname") == "OpenWrt"


@spec(CAPABILITY, "故障注入", "强制断电")
@target("emulation", "cuts the power without a shutdown")
def test_power_cut_keeps_the_disk(router: Router) -> None:
    emulator = router.emulator
    assert emulator is not None
    router.run("echo written-before-the-cut > /root/marker && sync")
    router.disconnect()
    emulator.power_cut()
    emulator.power_on()
    router.wait_ready()
    assert router.run("cat /root/marker") == "written-before-the-cut"
