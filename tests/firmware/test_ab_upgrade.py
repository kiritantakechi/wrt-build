"""firmware/ab-upgrade: an upgrade writes the other slot, hands the configuration on, tries it."""

import time
from typing import TYPE_CHECKING

from wrt_tests import spec
from wrt_tests.device.ab import boot_area_sha256, getenv, setenv, slot, slot_sha256
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
# An image whose every read waits: a FIFO, whose opening waits for a writer.
SLOW_IMAGE = "/tmp/slow-image"  # noqa: S108 (a path on the router)
VALIDATION = "/tmp/validation"  # noqa: S108 (a path on the router)
# How long the validation waits: longer than procd's watchdog timeout (30 s); and
# how long it may then take to end, the call's own limit.
SLOW_SECONDS = 45
VALIDATION_LIMIT = 300
# The upgrade hook, as sysupgrade's second stage loads it, in a shell of a test.
HOOK = ". /lib/functions.sh && include /lib/upgrade"
# An upgrade image cut short inside its root member, an uncompressed tar.
BROKEN_IMAGE = "/tmp/broken-image.tar"  # noqa: S108 (a path on the router)
BACKUP = "/tmp/backup.tgz"  # noqa: S108 (a path on the router)
# What the A/B switch writes, as it was before an upgrade.
SWITCH = ("boot_slot", "upgrade_available", "bootcount")
# How long the upgrade hook may take to write a slot.
WRITE_LIMIT = 600


def _upgrade(router: Router, image: Path, *options: str) -> None:
    """Run sysupgrade with ``image`` and wait until the router is back."""
    router.put(image, UPGRADE_IMAGE)
    previous_boot = router.boot_id()
    router.detach(f"sleep 1; sysupgrade {' '.join(options)} {UPGRADE_IMAGE}")
    router.wait_rebooted(previous_boot)


def _switch(router: Router) -> tuple[str | None, ...]:
    """Return what the A/B switch writes, as the U-Boot environment holds it now."""
    return tuple(getenv(router, name) for name in SWITCH)


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


@spec(CAPABILITY, "Trial boot after writing", "Write that fails")
def test_a_write_that_fails_keeps_the_running_slot(router: Router, upgrade_image: Path) -> None:
    running = slot(router)
    router.put(upgrade_image, UPGRADE_IMAGE)
    # The image unpacked and cut a tenth short, as it streams (/tmp is memory):
    # inside root, its last and largest member. BusyBox tar reads an archive to
    # its end whichever member it extracts, so every member's read then fails,
    # kernel's too, though its data came whole: the write stops at the kernel.
    router.run(
        f"size=$(gzip -dc {UPGRADE_IMAGE} | wc -c)"
        f" && gzip -dc {UPGRADE_IMAGE} | head -c $((size * 9 / 10)) >{BROKEN_IMAGE}",
        timeout=120,
    )
    # BusyBox tar reads no gzip on its own.
    members = router.run(f"gzip -dc {UPGRADE_IMAGE} | tar -tf -").split()
    (root,) = [member for member in members if member.endswith("/root")]
    assert router.returncode(f"tar -xOf {BROKEN_IMAGE} {root} >/dev/null 2>&1") != 0
    before = _switch(router)
    output = router.run(
        f"{HOOK} && platform_do_upgrade {BROKEN_IMAGE} 2>&1; echo exit=$?", timeout=WRITE_LIMIT
    )
    assert output.endswith("exit=1"), output
    assert _switch(router) == before
    previous_boot = router.boot_id()
    router.reboot()
    assert router.boot_id() != previous_boot
    assert slot(router) == running


@spec(CAPABILITY, "Trial boot after writing", "Configuration in place before the switch")
def test_the_configuration_is_in_place_before_the_switch(
    router: Router, upgrade_image: Path
) -> None:
    router.put(upgrade_image, UPGRADE_IMAGE)
    router.run(f"sysupgrade -b {BACKUP}", timeout=120)
    # The switch, recorded instead of written: whether the new slot's boot
    # partition (the hook's wrt_boot_dev) holds the backup when it comes.
    record = (
        'wrt_ab_setenv() { mount -o ro "/dev/${wrt_boot_dev}" /mnt'
        " && if [ -f /mnt/sysupgrade.tgz ]; then echo switch=backup-present;"
        " else echo switch=backup-absent; fi; umount /mnt; }"
    )
    output = router.run(
        f"{HOOK} && {record} && UPGRADE_BACKUP={BACKUP} BACKUP_FILE=sysupgrade.tgz"
        f" platform_do_upgrade {UPGRADE_IMAGE} 2>&1; echo exit=$?",
        timeout=WRITE_LIMIT,
    )
    assert "switch=backup-present" in output, output
    assert output.endswith("exit=0"), output


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


@spec(
    CAPABILITY,
    "The system stays responsive while it checks an image",
    "A validation slower than the watchdog",
)
def test_a_slow_validation_keeps_the_system_going(router: Router) -> None:
    emulator = router.emulator
    logged = len(emulator.logged())
    previous_boot = router.boot_id()
    router.run(f"mkfifo {SLOW_IMAGE}")
    request = f'{{"path": "{SLOW_IMAGE}"}}'
    router.detach(
        f"ubus -t {VALIDATION_LIMIT} call system validate_firmware_image '{request}'"
        f" > {VALIDATION} 2>&1;"
        f" echo exit=$? >> {VALIDATION}"
    )
    deadline = time.monotonic() + SLOW_SECONDS
    while time.monotonic() < deadline:
        router.run("ubus -t 10 call system board >/dev/null", timeout=30)
        time.sleep(5)
    assert router.boot_id() == previous_boot
    assert "watchdog_perform_action" not in emulator.logged()[logged:]
    # Each check that waits on the image now ends. One that reads it gets an empty
    # image from a writer, which opens and closes the FIFO again and again. One that
    # holds it read-write never sees the end of its input, being a writer itself
    # (fwtool), so it fails: its process ends.
    router.detach(f"while :; do : > {SLOW_IMAGE}; done")
    router.run(
        f"until grep -q '^exit=' {VALIDATION}; do for fd in /proc/[0-9]*/fd/*; do"
        f' [ "$(readlink "$fd")" = {SLOW_IMAGE} ] || continue; pid=${{fd#/proc/}};'
        " pid=${pid%%/*}; case $(sed -n 's/^flags:[[:space:]]*//p' /proc/$pid/fdinfo/${fd##*/})"
        ' in *2) kill "$pid";; esac; done 2>/dev/null; sleep 1; done',
        timeout=VALIDATION_LIMIT,
    )
    validation = router.run(f"cat {VALIDATION}")
    assert validation.endswith("exit=0")
    assert '"valid": false' in validation
