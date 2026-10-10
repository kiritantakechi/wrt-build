"""firmware/boot-rollback: U-Boot picks the slot, counts trial boots and rolls back."""

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from wrt_tests import spec
from wrt_tests.device.ab import (
    BOOT_DISK,
    ENV_OFFSET,
    ENV_SIZE,
    getenv,
    partition,
    region_sha256,
    setenv,
    slot,
)
from wrt_tests.device.emu import extract_fit_image, read_fit, run
from wrt_tests.model.image import SECTOR, default_environment, read_mbr

if TYPE_CHECKING:
    from wrt_tests.device.router import Router
    from wrt_tests.model.boards import Board

CAPABILITY = "firmware/boot-rollback"
UBOOT_DIR = Path(__file__).resolve().parents[2] / "uboot"
UBOOT_SECTOR = 16384
UBOOT_BANNER = r"U-Boot 20\d\d\.\d\d"
# Variables U-Boot itself defines for the slot logic, besides those of wrt-ab.env.
LOGIC = ("bootcmd", "altbootcmd", "bootlimit")
UPGRADE_IMAGE = "/tmp/sysupgrade.tar.gz"  # noqa: S108 (a path on the router)
BOOT_LIMIT = 3
PANIC_REBOOT = 10.0


def _names(env_file: Path) -> set[str]:
    """Return the variables an environment source file defines."""
    return set(re.findall(r"^([A-Za-z_]\w*)=", env_file.read_text(), re.MULTILINE))


def _trial(router: Router) -> None:
    """Put the running slot in the trial state, with the health check out of the way."""
    router.run("/etc/init.d/wrt-healthcheck disable")
    setenv(router, boot_slot=slot(router), upgrade_available=1, bootcount=0)


def _env_sha256(router: Router) -> str:
    return region_sha256(router, BOOT_DISK, ENV_OFFSET, ENV_OFFSET + ENV_SIZE)


def _config(path: Path) -> dict[str, str]:
    """Return the options a Kconfig configuration sets."""
    return dict(
        line.split("=", 1) for line in path.read_text().splitlines() if line.startswith("CONFIG_")
    )


def _board_uboot(emulation_dir: Path, tmp_path: Path) -> tuple[Path, Path]:
    """Extract the shipped U-Boot of the factory image: its binary and control device tree."""
    disk = emulation_dir / "disk.raw"
    with disk.open("rb") as raw:
        first = read_mbr(raw.read(SECTOR)).partitions[0].start
        raw.seek(UBOOT_SECTOR * SECTOR)
        itb = tmp_path / "u-boot.itb"
        itb.write_bytes(raw.read(first - UBOOT_SECTOR * SECTOR))
    fit = read_fit(itb)
    binary, dtb = tmp_path / "u-boot.bin", tmp_path / "u-boot.dtb"
    extract_fit_image(itb, fit.images["u-boot"], binary)
    extract_fit_image(itb, fit.selected("FDT"), dtb)
    return binary, dtb


@spec(CAPABILITY, "Slot selection from a persistent variable", "Select slot B")
def test_boot_slot_b(router: Router) -> None:
    setenv(router, boot_slot="b")
    router.reboot()
    assert slot(router) == "b"
    root = router.run("sed -n 's/.*root=PARTUUID=\\([0-9a-f-]*\\).*/\\1/p' /proc/cmdline")
    assert root.endswith("-04")
    assert router.run("awk '$2 == \"/rom\" { print $1 }' /proc/mounts") in {
        "/dev/root",
        partition(4),
    }


@spec(
    CAPABILITY,
    "Slot selection from a persistent variable",
    "Persistent variable missing or corrupted",
)
def test_corrupted_environment_boots_slot_a(router: Router) -> None:
    setenv(router, boot_slot="b")
    # Overwrite the CRC and the first variables: U-Boot falls back to its defaults.
    router.run(
        f"dd if=/dev/urandom of={BOOT_DISK} bs=64 seek={ENV_OFFSET // 64} count=1 conv=fsync"
    )
    router.reboot()
    assert slot(router) == "a"


@spec(
    CAPABILITY,
    "Persistent environment cannot override boot logic",
    "Custom boot command in persistent environment",
)
def test_stored_boot_command_is_ignored(router: Router) -> None:
    console = router.emulator.console
    since = console.mark()
    setenv(router, boot_slot="b", bootcmd="echo wrt-hijacked", wrt_boot="echo wrt-hijacked")
    router.reboot()
    assert slot(router) == "b"
    assert "wrt-hijacked" not in console.text(since)


@spec(CAPABILITY, "Trial boot counting and automatic rollback", "New slot fails repeatedly")
def test_rollback_after_three_unconfirmed_boots(router: Router, upgrade_image: Path) -> None:
    # The new slot inherits a configuration that keeps its web server off the LAN,
    # so its health check fails every time, quickly.
    router.run(
        "uci set uhttpd.main.listen_http=127.0.0.1:80"
        " && uci set wrt-ab.healthcheck.total=10 && uci set wrt-ab.healthcheck.interval=5"
        " && uci commit"
    )
    console = router.emulator.console
    since = console.mark()
    router.put(upgrade_image, UPGRADE_IMAGE)
    router.detach(f"sleep 1; sysupgrade {UPGRADE_IMAGE}")
    console.wait_for(rf"Bootlimit \({BOOT_LIMIT}\) exceeded", since=since, timeout=1800)
    router.wait_ssh()
    router.wait_ready()
    assert slot(router) == "a"
    assert (getenv(router, "boot_slot"), getenv(router, "upgrade_available")) == ("a", "0")
    assert getenv(router, "bootcount") == "0"
    # The failed slot booted exactly bootlimit times after the upgrade.
    assert len(re.findall(r"wrt\.slot=b", console.text(since))) == BOOT_LIMIT


@spec(
    CAPABILITY, "Trial boot counting and automatic rollback", "No counting during normal operation"
)
def test_confirmed_boot_writes_nothing(router: Router) -> None:
    assert getenv(router, "upgrade_available") in {None, "0"}
    before = (_env_sha256(router), getenv(router, "bootcount"))
    router.reboot()
    assert (_env_sha256(router), getenv(router, "bootcount")) == before


@spec(CAPABILITY, "Trial boot counting and automatic rollback", "Current slot fails to load")
def test_fallback_within_one_power_cycle(router: Router) -> None:
    emulator = router.emulator
    router.run(f"mount {partition(3)} /mnt && rm /mnt/kernel.img && umount /mnt")
    setenv(router, boot_slot="b")
    router.reboot()
    assert slot(router) == "a"
    assert getenv(router, "boot_slot") == "b"
    # With neither slot loadable U-Boot gives up at its prompt, and stays there.
    router.run(f"mount {partition(1)} /mnt && rm /mnt/kernel.img && umount /mnt && sync")
    since = emulator.console.mark()
    router.detach("sleep 1; reboot")
    emulator.console.wait_for(
        "neither slot boots, stopping at the prompt", since=since, timeout=300
    )
    prompt = emulator.console.mark()
    time.sleep(30)
    assert not re.search(UBOOT_BANNER, emulator.console.text(prompt))


@spec(CAPABILITY, "Hangs and panics become reboots", "Kernel panic")
def test_panic_reboots_and_counts(router: Router) -> None:
    _trial(router)
    console = router.emulator.console
    previous_boot = router.boot_id()
    since = console.mark()
    router.detach("sleep 1; echo c > /proc/sysrq-trigger")
    console.wait_for(r"Kernel panic", since=since, timeout=60)
    panicked = time.monotonic()
    console.wait_for(UBOOT_BANNER, since=console.mark(), timeout=15)
    assert time.monotonic() - panicked < PANIC_REBOOT
    router.wait_rebooted(previous_boot)
    assert getenv(router, "bootcount") == "1"


@spec(CAPABILITY, "Hangs and panics become reboots", "Userspace stops feeding the watchdog")
def test_watchdog_resets_a_hung_userspace(router: Router) -> None:
    _trial(router)
    previous_boot = router.boot_id()
    router.run("ubus call system watchdog '{\"stop\": true}'")
    router.wait_rebooted(previous_boot)
    assert slot(router) == "a"
    assert getenv(router, "bootcount") == "1"


@spec(CAPABILITY, "Hangs and panics become reboots", "Watchdog armed before the kernel")
def test_watchdog_chain_configuration(
    build_output: Path, emulation_dir: Path, tmp_path: Path
) -> None:
    uboot = (build_output / "u-boot.config").read_text().splitlines()
    for line in (
        "CONFIG_WDT=y",
        "CONFIG_WATCHDOG_AUTOSTART=y",
        "CONFIG_WATCHDOG_TIMEOUT_MSECS=60000",
        "CONFIG_DESIGNWARE_WATCHDOG=y",
    ):
        assert line in uboot, line
    kernel = (build_output / "kernel.config").read_text().splitlines()
    for line in ("CONFIG_DW_WATCHDOG=y", "CONFIG_WATCHDOG_HANDLE_BOOT_ENABLED=y"):
        assert line in kernel, line
    binary, _ = _board_uboot(emulation_dir, tmp_path)
    assert (
        "watchdog.open_timeout=90"
        in default_environment(binary.read_bytes(), "wrt_boot")["wrt_boot"]
    )


@spec(
    CAPABILITY, "Same slot logic on the device and in the emulator", "Compare the two bootloaders"
)
def test_same_logic_in_both_bootloaders(
    board: Board, build_output: Path, emulation_dir: Path, tmp_path: Path
) -> None:
    binary, dtb = _board_uboot(emulation_dir, tmp_path)
    shipped = default_environment(binary.read_bytes(), "wrt_boot")
    qemu = default_environment((build_output / "u-boot-qemu.bin").read_bytes(), "wrt_boot")
    shared = _names(UBOOT_DIR / "wrt-ab.env") | set(LOGIC)
    constants = _names(UBOOT_DIR / f"board-{board.id}.env")
    assert constants == _names(UBOOT_DIR / "board-qemu.env")
    assert {name: shipped[name] for name in shared} == {name: qemu[name] for name in shared}
    assert constants <= shipped.keys() & qemu.keys()
    # Each keeps its environment at the shared offset of the MMC device its
    # constants boot from...
    for name, environment in (("u-boot.config", shipped), ("u-boot-qemu.config", qemu)):
        config = _config(build_output / name)
        assert config.get("CONFIG_ENV_IS_IN_MMC") == "y", name
        assert int(config["CONFIG_ENV_MMC_DEVICE_INDEX"]) == int(environment["wrt_mmc"]), name
        assert int(config["CONFIG_ENV_OFFSET"], 16) == ENV_OFFSET, name
        assert int(config["CONFIG_ENV_SIZE"], 16) == ENV_SIZE, name
    # ...which the board's device tree makes its boot disk's controller: an eMMC
    # is soldered on, an SD card is not.
    assert run("fdtget", str(dtb), "/", "compatible").split()[0] == board.board_name
    controller = run("fdtget", str(dtb), "/aliases", f"mmc{shipped['wrt_mmc']}").strip()
    properties = run("fdtget", "-p", str(dtb), controller).split()
    assert ("non-removable" in properties) == (board.boot_disk == "emmc"), controller
