"""firmware/base-system: LAN address, LuCI, shells, zram and what the image leaves out."""

import re
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

from wrt_tests import spec, target

if TYPE_CHECKING:
    from wrt_tests.router import Router

CAPABILITY = "firmware/base-system"
DEFAULT_LAN = "10.0.0.1"
EXCLUDED_PACKAGES = (
    "urngd",
    "opkg",
    "shortcut-fe",
    "natflow",
    "lrng",
    "libpcre",
    "upx",
    "nginx",
    "uwsgi",
)
EXECUTABLE_DIRS = "/rom/bin /rom/sbin /rom/usr/bin /rom/usr/sbin /rom/lib /rom/usr/lib"
FAILSAFE_PROMPT = r"Press the \[f\] key and hit \[enter\] to enter failsafe mode"
BOOT_TIMEOUT = 600.0
UPGRADE_IMAGE = "/tmp/sysupgrade.img.gz"  # noqa: S108 (a path on the router)


def _report(output: str) -> str:
    """Return the value of the ``@@ <value>`` line a login script echoed."""
    match = re.search(r"^@@ (.*?)\s*$", output, re.MULTILINE)
    assert match is not None, output
    return str(match.group(1))


def _installed(router: Router, *names: str) -> set[str]:
    """Return which of ``names`` are installed, also as ``<name>-*`` or ``kmod-<name>``."""
    installed = router.run("apk info").split()
    return {
        package
        for package in installed
        for name in names
        if package in {name, f"kmod-{name}"} or package.startswith(f"{name}-")
    }


@spec(CAPABILITY, "Default LAN address", "Fresh install")
def test_default_lan_address(router: Router) -> None:
    assert f"inet {DEFAULT_LAN}/24 " in router.run("ip -4 addr show dev br-lan")


@spec(CAPABILITY, "Default LAN address", "Enter failsafe mode")
@target("emulation", "types the failsafe key on the serial console")
def test_failsafe_address(router: Router) -> None:
    emulator = router.emulator
    assert emulator is not None
    since = emulator.console.mark()
    router.detach("sleep 1; reboot")
    emulator.console.wait_for(FAILSAFE_PROMPT, since=since, timeout=BOOT_TIMEOUT)
    emulator.send_keys("f\n")
    emulator.console.wait_for(r"- failsafe -", since=since, timeout=120)
    router.wait_ssh()
    assert router.returncode("[ -e /tmp/.failsafe ]") == 0
    assert f"inet {DEFAULT_LAN}/" in router.run("ip -4 addr")


@spec(CAPABILITY, "Default LAN address", "Config-preserving upgrade")
@target("emulation", "upgrades the emulated disk with the image under test")
def test_upgrade_keeps_the_lan_address(router: Router, emulation_source: dict[str, str]) -> None:
    router.run("uci set network.lan.ipaddr=10.0.0.3/24 && uci commit network")
    # The zram defaults are only filled in while unset (uci-defaults), so an
    # administrator's value survives the upgrade as well.
    router.run("uci set system.@system[0].zram_size_mb=512 && uci commit system")
    router.put(Path(emulation_source["image"]), UPGRADE_IMAGE)
    previous_boot = router.boot_id()
    router.detach(f"sleep 1; sysupgrade {UPGRADE_IMAGE}")
    with router.moved_to("10.0.0.3"):
        router.wait_rebooted(previous_boot)
        assert router.run("uci get network.lan.ipaddr") == "10.0.0.3/24"
        assert "inet 10.0.0.3/24 " in router.run("ip -4 addr show dev br-lan")
        assert router.run("uci get system.@system[0].zram_size_mb") == "512"


@spec(CAPABILITY, "Web management interface", "Open the management interface")
def test_luci_in_simplified_chinese(router: Router) -> None:
    # LuCI keeps lang 'auto' and follows the browser; without a session it answers
    # with its login page and 403 (login required).
    status, page = router.http("/cgi-bin/luci/", headers={"Accept-Language": "zh-CN,zh;q=0.9"})
    assert status in {HTTPStatus.OK, HTTPStatus.FORBIDDEN}
    assert "/luci-static/" in page
    assert re.search(r'<html[^>]*\blang="zh-(cn|hans)"', page, re.IGNORECASE), page[:300]
    assert "uhttpd" in router.run("ss -Hltnp 'sport = :80'")


@spec(CAPABILITY, "Web management interface", "No nginx or uwsgi")
def test_no_nginx_or_uwsgi(router: Router) -> None:
    assert _installed(router, "nginx", "uwsgi") == set()


@spec(CAPABILITY, "Interactive shell", "Interactive SSH login")
def test_interactive_login_is_zsh_with_plugins(router: Router) -> None:
    output = router.login(
        'echo "@@ $(readlink /proc/$$/exe) '
        '${+functions[_zsh_autosuggest_start]} ${+functions[_zsh_highlight]}"\nexit\n'
    )
    assert _report(output) == "/usr/bin/zsh 1 1"


@spec(CAPABILITY, "Interactive shell", "Non-interactive command")
def test_remote_command_runs_in_ash(router: Router) -> None:
    assert router.run("readlink /proc/$$/exe") == "/bin/busybox"
    assert router.run('echo "${ZSH_VERSION:-none}"') == "none"


@spec(CAPABILITY, "Interactive shell", "zsh unavailable")
def test_login_stays_in_ash_without_zsh(router: Router) -> None:
    router.run("chmod -x /usr/bin/zsh")
    try:
        output = router.login('echo "@@ $(readlink /proc/$$/exe)"\nexit\n')
    finally:
        router.run("chmod +x /usr/bin/zsh")
    assert _report(output) == "/bin/busybox"


@spec(CAPABILITY, "Interactive shell", "Enter bash manually")
def test_bash_login_stays_in_bash(router: Router) -> None:
    output = router.login('bash -l\necho "@@ $(readlink /proc/$$/exe)"\nexit\nexit\n')
    assert _report(output) == "/bin/bash"


@spec(CAPABILITY, "Compressed memory swap", "Check swap device")
def test_zram_swap(router: Router) -> None:
    swaps = router.run("cat /proc/swaps")
    assert re.search(r"^/dev/zram0\s+partition\s+1048572\s", swaps, re.MULTILINE), swaps
    assert "[zstd]" in router.run("cat /sys/block/zram0/comp_algorithm")


@spec(CAPABILITY, "No preset password", "Check shadow file")
def test_no_preset_root_password(router: Router) -> None:
    # /rom holds the image as shipped, whatever the administrator set since.
    assert router.run("awk -F: '$1 == \"root\" { print $2 }' /rom/etc/shadow") == ""


@spec(CAPABILITY, "Excluded components", "Check installed packages and executables")
def test_excluded_components(router: Router) -> None:
    assert _installed(router, *EXCLUDED_PACKAGES) == set()
    assert router.returncode("ls /proc/lrng_type /proc/sys/kernel/random/lrng_type") != 0
    # Executables and libraries only: grepping every file is too slow under TCG.
    upx = router.run(
        f"find {EXECUTABLE_DIRS} -type f -perm -100 -exec grep -l 'UPX!' {{}} + 2>/dev/null"
        " || true",
        timeout=600,
    )
    assert upx == ""
