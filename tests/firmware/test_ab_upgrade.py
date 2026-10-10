"""firmware/ab-upgrade: an upgrade writes the other slot, hands the configuration on, tries it."""

from typing import TYPE_CHECKING

from wrt_tests import spec
from wrt_tests.device.ab import boot_area_sha256, setenv, slot, slot_sha256
from wrt_tests.model.boards import load_all

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.device.router import Router
    from wrt_tests.model.boards import Board

CAPABILITY = "firmware/ab-upgrade"
UPGRADE_IMAGE = "/tmp/sysupgrade.tar.gz"  # noqa: S108 (a path on the router)
# Slow enough that a power cut lands in the middle of writing a slot.
THROTTLED_WRITE = 2 << 20
HOSTNAME = "upgraded"


def _upgrade(router: Router, image: Path, *options: str) -> None:
    """Run sysupgrade with ``image`` and wait until the router is back."""
    router.put(image, UPGRADE_IMAGE)
    previous_boot = router.boot_id()
    router.detach(f"sleep 1; sysupgrade {' '.join(options)} {UPGRADE_IMAGE}")
    router.wait_rebooted(previous_boot)


def _confirmed(router: Router, which: str) -> None:
    """Wait until the health check has confirmed the trial slot ``which``."""
    message = f"slot {which} passed its trial boot and is confirmed"
    router.run(
        f"until logread -e wrt-healthcheck | grep -q '{message}'; do sleep 2; done", timeout=400
    )


@spec(CAPABILITY, "Write only the inactive slot", "Upgrade from slot A")
def test_upgrade_writes_only_slot_b(router: Router, upgrade_image: Path) -> None:
    before = (slot_sha256(router, "a"), boot_area_sha256(router))
    _upgrade(router, upgrade_image)
    assert slot(router) == "b"
    assert (slot_sha256(router, "a"), boot_area_sha256(router)) == before


@spec(CAPABILITY, "Write only the inactive slot", "Power loss mid-upgrade")
def test_power_loss_keeps_slot_a(router: Router, upgrade_image: Path) -> None:
    emulator = router.emulator
    router.put(upgrade_image, UPGRADE_IMAGE)
    emulator.throttle_writes(THROTTLED_WRITE)
    since = emulator.console.mark()
    router.detach(f"sleep 1; sysupgrade {UPGRADE_IMAGE}")
    emulator.console.wait_for("Writing slot b", since=since, timeout=300)
    router.disconnect()
    emulator.power_cut()
    emulator.power_on()
    router.wait_ready()
    assert slot(router) == "a"


@spec(CAPABILITY, "New slot starts with a fresh overlay", "Leftover file in the old overlay")
def test_new_slot_starts_fresh(router: Router, upgrade_image: Path) -> None:
    setenv(router, boot_slot="b")
    router.reboot()
    router.run("echo old > /root/leftover && sync")
    setenv(router, boot_slot="a")
    router.reboot()
    _upgrade(router, upgrade_image)
    assert slot(router) == "b"
    assert router.returncode("[ -e /root/leftover ]") != 0


@spec(CAPABILITY, "Config migration", "Config-preserving upgrade")
def test_upgrade_keeps_the_configuration(router: Router, upgrade_image: Path) -> None:
    router.run(f"uci set system.@system[0].hostname={HOSTNAME} && uci commit system")
    _upgrade(router, upgrade_image)
    assert slot(router) == "b"
    assert router.run("uci get system.@system[0].hostname") == HOSTNAME


@spec(CAPABILITY, "Config migration", "Upgrade without preserving config")
def test_upgrade_without_the_configuration(router: Router, upgrade_image: Path) -> None:
    router.run(f"uci set system.@system[0].hostname={HOSTNAME} && uci commit system")
    _upgrade(router, upgrade_image, "-n")
    assert slot(router) == "b"
    assert router.run("uci get system.@system[0].hostname") == "OpenWrt"


@spec(CAPABILITY, "Trial boot after writing", "Reboot after upgrade")
def test_upgrade_boots_the_new_slot_on_trial(router: Router, upgrade_image: Path) -> None:
    _upgrade(router, upgrade_image)
    assert slot(router) == "b"
    _confirmed(router, "b")


@spec(CAPABILITY, "Reject mismatched images", "Image for another device")
def test_image_for_another_board_is_rejected(
    router: Router, board: Board, upgrade_image: Path
) -> None:
    router.put(upgrade_image, UPGRADE_IMAGE)
    # Rewrite the metadata so that the image names another supported board only.
    other = next(other for other in load_all() if other.id != board.id)
    router.run(
        f"fwtool -q -t -i /tmp/meta.json {UPGRADE_IMAGE}"
        f" && sed -i 's/{board.board_name}/{other.board_name}/' /tmp/meta.json"
        f" && fwtool -I /tmp/meta.json {UPGRADE_IMAGE}"
    )
    before = (slot_sha256(router, "a"), slot_sha256(router, "b"))
    previous_boot = router.boot_id()
    output = router.run(f"sysupgrade {UPGRADE_IMAGE} 2>&1; echo exit=$?", timeout=120)
    assert "not supported by this image" in output
    assert output.endswith("exit=1")
    assert router.boot_id() == previous_boot
    assert (slot_sha256(router, "a"), slot_sha256(router, "b")) == before


@spec(CAPABILITY, "Manual slot switch", "Manually roll back to the previous version")
def test_manual_switch_back_to_slot_a(router: Router, upgrade_image: Path) -> None:
    _upgrade(router, upgrade_image)
    _confirmed(router, "b")
    previous_boot = router.boot_id()
    router.detach("sleep 1; wrt-slot switch")
    router.wait_rebooted(previous_boot)
    assert slot(router) == "a"
    _confirmed(router, "a")
