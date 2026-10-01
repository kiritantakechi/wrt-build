"""storage/data-disk: the USB data disk, what waits for it, and what goes on without it.

The module's data disk is a blank image made the data disk with ``wrt-data init``
(the ``data_disk`` fixture); the app Pod is declared on it, so that the container
service has something to start. A spare disk comes and goes for the tests that
need a second one. The tests that boot without the data disk come last: they
share one boot, and the last of them plugs the disk back in. The data disk comes
and goes only while the router is off, as a disk is best moved: pulled out while
in use, it would lose what was not written out yet.
"""

import json
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from wrt_tests import app, spec
from wrt_tests.net import DIRECT_TARGET, PROXIED_TARGET, PROXY
from wrt_tests.poll import until
from wrt_tests.storage import (
    MOUNT,
    PLUG_TIMEOUT,
    SUBVOLUMES,
    Disk,
    device,
    initialize,
    mount_options,
    subvolumes,
    wait_mounted,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.datapath import Online
    from wrt_tests.emu import Emulator
    from wrt_tests.router import Router

CAPABILITY = "storage/data-disk"
SERVICES_DOC = Path(__file__).resolve().parents[2] / "docs" / "services.md"
LOG = f"{MOUNT}/logs/messages"
SNAPSHOTS = f"{MOUNT}/.snapshots"
SNAPSHOTTED = ("containers", "shares")
KEEP_DAYS = 7
DAYS_RUN = 9  # more than eight days
CRON_TIMEOUT = 90
# The boot disk's own directory under the mount point: the overlay's upper layer.
BOOT_DISK = f"/overlay/upper{MOUNT}"
HEALTHCHECK = (
    "uci set wrt-ab.healthcheck.total=30 && uci set wrt-ab.healthcheck.interval=3"
    " && uci commit wrt-ab && wrt-healthcheck"
)
HEALTH = "/var/run/wrt-healthcheck.json"


@pytest.fixture(scope="module")
def pod(app_pod: Online) -> Online:
    """Return the module's router online, with the app Pod on its data disk."""
    return app_pod


@pytest.fixture
def spare(emulator: Emulator, tmp_path: Path) -> Iterator[Disk]:
    """Provide a second blank disk, pulled out after the test."""
    disk = Disk.blank(emulator, tmp_path, "spare")
    yield disk
    disk.unplug()


@pytest.fixture(scope="module")
def rebooted(pod: Online) -> str:
    """Leave a line in the persistent log, then reboot; return the line."""
    router = pod.router
    line = f"before the reboot {time.time_ns()}"
    router.run(f"logger -t data-disk-test {line!r}")
    until(
        lambda: router.returncode(f"grep -qF {line!r} {LOG}") == 0,
        timeout=30,
        what="the line in the persistent log",
    )
    pod.reboot()
    return line


def _boot_disk_entries(router: Router) -> list[str]:
    """Return what the boot disk itself holds under /mnt/data."""
    return router.run(f"ls -A {BOOT_DISK} 2>/dev/null || true").split()


def _services(router: Router) -> dict[str, bool]:
    """Return which of the services on the data disk run.

    Asking podman itself would have it create its storage wherever the data
    disk is not: a running container is a conmon.
    """
    return {
        "containers": router.returncode("pidof conmon >/dev/null") == 0,
        "file sharing": router.returncode("pidof ksmbd.mountd >/dev/null") == 0,
        "persistent log": router.returncode(f"test -e {LOG}") == 0,
    }


def _kept(router: Router) -> dict[str, list[str]]:
    """Return the days of each snapshotted subvolume's snapshots, once cron's job is done.

    The job runs as a child of crond, both of its commands.
    """
    if router.returncode('pgrep -P "$(pidof crond)" >/dev/null') == 0:
        return {}
    return {
        subvolume: [
            path.rsplit("/", 1)[1][:8]
            for path in router.run(f"wrt-snap list {subvolume}").splitlines()
        ]
        for subvolume in SNAPSHOTTED
    }


@spec(CAPABILITY, "Btrfs data disk and subvolume layout", "Check mounts")
def test_mounts(rebooted: str, pod: Online, spare: Disk) -> None:
    del rebooted  # the boot to check
    router = pod.router
    options = mount_options(router)
    assert options is not None
    assert {"compress=zstd:3", "noatime", "space_cache=v2"} <= options
    assert {*SUBVOLUMES, ".snapshots"} <= subvolumes(router)
    for subvolume in SUBVOLUMES:
        assert router.returncode(f"btrfs subvolume show {MOUNT}/{subvolume} >/dev/null") == 0

    # wrt-data init erases nothing that was not confirmed.
    spare.plug(3)
    assert initialize(router, spare, answer="no") != 0
    assert initialize(router, spare, answer=device(router, spare).removeprefix("/dev/")) != 0
    assert spare.blank_still


@spec(CAPABILITY, "Persistent logs on the data disk", "View logs after reboot")
def test_logs_survive_reboot(rebooted: str, pod: Online) -> None:
    router = pod.router
    assert router.returncode(f"cat {LOG}* | grep -qF {rebooted!r}") == 0
    assert router.run("uci get system.@system[0].log_size") == "65536"


@spec(CAPABILITY, "Periodic read-only snapshots", "Manual snapshot")
def test_manual_snapshot(pod: Online) -> None:
    router = pod.router
    before = int(router.run("date +%s"))
    taken = router.run("wrt-snap now").splitlines()
    after = int(router.run("date +%s"))
    assert [path.split("/")[-2] for path in taken] == list(SNAPSHOTTED)
    for path in taken:
        at = datetime.strptime(path.rsplit("/", 1)[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        assert before <= at.timestamp() <= after
        assert router.run(f"btrfs property get -ts {path} ro") == "ro=true"
    assert set(router.run("wrt-snap list").splitlines()) >= set(taken)


@spec(CAPABILITY, "Periodic read-only snapshots", "Restore a file from a snapshot")
def test_restore_a_file(pod: Online) -> None:
    router = pod.router
    commands = _documented_restore()
    (file,) = re.findall(r"^file=(\S+)$", commands, re.MULTILINE)
    content = f"{time.time_ns()}"
    path = f"{MOUNT}/shares/{file}"
    router.run(f"mkdir -p {path.rsplit('/', 1)[0]} && echo {content} >{path} && wrt-snap now")
    router.run(f"rm {path}")
    router.run(commands)
    assert router.run(f"cat {path}") == content


def _documented_restore() -> str:
    """Return the commands docs/services.md gives for restoring a file."""
    text = SERVICES_DOC.read_text()
    section = text.split("### Restore a file from a snapshot", 1)[1]
    block = re.search(r"```sh\n(.*?)```", section, re.DOTALL)
    assert block is not None
    return str(block.group(1))


@spec(CAPABILITY, "Periodic read-only snapshots", "Expired snapshots are pruned")
def test_expired_snapshots_are_pruned(pod: Online) -> None:
    router = pod.router
    today = datetime.fromtimestamp(int(router.run("date +%s")), UTC).date()
    dates = [today + timedelta(days=day) for day in range(1, DAYS_RUN + 1)]
    days = [f"{date:%Y%m%d}" for date in dates]
    try:
        for date, day in zip(dates, days, strict=True):
            # Half a minute before the daily job (03:17). cron starts afresh at the
            # new time and runs a job only when its minute begins, never late: a
            # restart still running at 03:17:00 on a busy emulator would miss it.
            router.run(f"date -u -s '{date} 03:16:30' >/dev/null && /etc/init.d/cron restart")
            until(
                lambda d=day: d in _kept(router).get("shares", []),
                timeout=CRON_TIMEOUT,
                what=f"the daily job of {date}",
            )
    finally:
        router.run(f"date -u -s @{int(time.time())} >/dev/null && /etc/init.d/cron restart")
    assert _kept(router) == dict.fromkeys(SNAPSHOTTED, days[-KEEP_DAYS:])


@spec(CAPABILITY, "Data disk identified by UUID", "Move to another USB port")
def test_moves_to_another_port(pod: Online, data_disk: Disk) -> None:
    def move() -> None:
        data_disk.unplug()
        data_disk.plug(2)

    pod.reboot(while_off=move)
    assert mount_options(pod.router) is not None
    assert {*SUBVOLUMES, ".snapshots"} <= subvolumes(pod.router)


@pytest.fixture(scope="module")
def without_disk(pod: Online, data_disk: Disk, dae: Online) -> Iterator[Online]:
    """Boot without the data disk, dae on; plug the disk back in at the end, if no test did."""
    del dae  # enabled, it starts with the boot
    pod.reboot(while_off=data_disk.unplug)
    yield pod
    if data_disk.port is None:
        data_disk.plug(1)
        wait_mounted(pod.router)


@spec(CAPABILITY, "Degraded mode without the data disk", "Boot without the data disk")
def test_boot_without_the_data_disk(without_disk: Online) -> None:
    router = without_disk.router
    client = without_disk.client()
    assert client.probe("tcp", DIRECT_TARGET[0])["address"] == without_disk.wan_address
    assert client.probe("tcp", PROXIED_TARGET[0])["address"] == PROXY[0]
    resolved = client.probe("resolve", "direct.example.net", "--server", router.address)
    assert resolved["answers"] == [DIRECT_TARGET[0]]
    assert mount_options(router) is None
    # The log service restarted without the disk (as any change to the system
    # configuration does) still keeps its file off the boot disk.
    router.run("/etc/init.d/log restart")
    services = _services(router)
    assert not any(services.values()), services
    assert _boot_disk_entries(router) == []
    router.run(HEALTHCHECK, timeout=180)
    assert json.loads(router.run(f"cat {HEALTH}"))["result"] == "pass"


@spec(CAPABILITY, "Data disk identified by UUID", "Insert another disk")
def test_other_disk_is_not_mounted(without_disk: Online, spare: Disk) -> None:
    router = without_disk.router
    # The same label as the data disk, and a filesystem of its own (another UUID).
    spare.plug(3)
    router.run(f"mkfs.btrfs -q -f -L wrtdata {device(router, spare)}", timeout=120)
    spare.unplug()
    spare.plug(3)
    path = device(router, spare)
    until(lambda: path in router.run("block info"), timeout=PLUG_TIMEOUT, what=f"{path} probed")
    router.run("block mount")
    assert mount_options(router) is None
    assert router.returncode(f"grep -q '^{path} ' /proc/mounts") != 0


@spec(CAPABILITY, "Dependent services wait for the mount", "Data disk mounts late")
def test_data_disk_mounts_late(without_disk: Online, data_disk: Disk) -> None:
    router = without_disk.router
    services = _services(router)
    assert not any(services.values()), services
    data_disk.plug(1)
    wait_mounted(router)
    app.wait_running(router)
    until(
        lambda: all(_services(router).values()),
        timeout=app.START_TIMEOUT,
        what="every service on the data disk",
    )
    assert _boot_disk_entries(router) == []
