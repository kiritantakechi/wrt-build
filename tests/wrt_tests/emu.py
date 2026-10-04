"""The emulated board (design D14, r4s-ab-rollback D7, board-model D7): its files and driving it.

``emu-prepare`` turns the outputs of a build into what the emulator boots, as the
board the build is for: the factory image as the board's kind of boot disk (an
SD card or an eMMC), which every test run overlays with copy-on-write; the
emulator's U-Boot as firmware; a device tree with the board's identity, which
U-Boot hands on to the kernel it starts from the slot; and the labgrid target
description of the machine, from the board's description. The output directory
is keyed by the image, the firmware and the board, and reused; directories of
builds that have since changed are removed.

``Emulator`` gives the tests power, disk snapshots and the serial console.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import yaml
from pexpect import TIMEOUT

from wrt_tests.boards import Board, load
from wrt_tests.image import SECTOR, Fit, FitNode, gunzip_first_member, parse_fit, read_mbr
from wrt_tests.net import segments, taps

if TYPE_CHECKING:
    from labgrid import Target
    from labgrid.driver import QEMUDriver

MANIFEST_FILE = "manifest.json"
FACTORY_IMAGE = "targets/*-factory.img.gz"
FIRMWARE = "u-boot-qemu.bin"
# The files of an emulator directory.
DISK_FILE = "disk.raw"
OVERLAY_FILE = "overlay.qcow2"
FIRMWARE_FILE = "u-boot.bin"
DTB_FILE = "board.dtb"
SOURCE_FILE = "source.json"
TARGET_FILE = "target.yaml"
QEMU = "qemu-system-aarch64"
MACHINE = "virt,gic-version=3"
# The boot disk's device, which throttle_writes() slows down.
BOOT_DISK_ID = "boot-disk"
# The router's LAN address, which the harness logs in to.
ROUTER_ADDRESS = "10.0.0.1"
UNPLUG_TIMEOUT = 30


@dataclass(frozen=True, slots=True)
class BootDisk:
    """A kind of boot disk as the emulator attaches it.

    ``device`` is QEMU's device on the SD host controller, ``size`` the disk's size,
    a power of two as QEMU wants it.
    """

    device: str
    size: int


# An SD card as small as an image must fit, and an eMMC as large as the boards'.
BOOT_DISKS = {"sd": BootDisk("sd-card", 4 << 30), "emmc": BootDisk("emmc", 32 << 30)}


@dataclass(frozen=True, slots=True)
class Machine:
    """The QEMU machine that stands in for a board (board-model D7)."""

    board: Board

    def dump_dtb(self, output: Path, firmware: Path) -> None:
        """Write the device tree QEMU generates for this machine running ``firmware``.

        The firmware belongs to the machine: with one, QEMU replaces the PL061 GPIO
        with an ACPI event device, and a device tree without it would describe a
        device the kernel faults on.
        """
        emulator, cores = self.board.emulator, len(self.board.soc.cores)
        subprocess.run(
            [
                QEMU,
                *("-machine", f"{MACHINE},dumpdtb={output}"),
                *("-cpu", emulator.cpu, "-m", emulator.memory, "-smp", str(cores)),
                *("-bios", str(firmware)),
                "-nographic",
            ],
            check=True,
            capture_output=True,
        )

    def description(self, directory: Path) -> dict[str, Any]:
        """Return the labgrid target description of the machine booting ``directory``'s files.

        The boot disk is the board's kind on an SD host controller; each of the
        board's ports is a virtio NIC in the board's order, on its segment's tap.
        The xHCI controller takes the USB data disks the tests plug in and out
        (r4s-services D10).
        """
        emulator = self.board.emulator
        nics = [
            argument
            for index, (segment, tap) in enumerate(
                zip(segments(self.board), taps(self.board), strict=True)
            )
            for argument in (
                f"-netdev tap,id={segment},ifname={tap},script=no,downscript=no",
                f"-device virtio-net-pci,netdev={segment},mac=52:54:00:0a:00:{0x10 + index:02x}",
            )
        ]
        arguments = (
            f"-smp {len(self.board.soc.cores)}",
            f"-drive if=none,id=disk,format=qcow2,file={directory / OVERLAY_FILE}",
            "-device sdhci-pci",
            f"-device {BOOT_DISKS[self.board.boot_disk].device},id={BOOT_DISK_ID},drive=disk",
            *nics,
            "-device i6300esb",
            "-device qemu-xhci,id=xhci",
            "-action watchdog=reset",
        )
        return {
            "targets": {
                "main": {
                    "resources": {
                        "NetworkService": {"address": ROUTER_ADDRESS, "username": "root"},
                    },
                    "drivers": {
                        "QEMUDriver": {
                            "qemu_bin": "qemu",
                            "machine": MACHINE,
                            "cpu": emulator.cpu,
                            "memory": emulator.memory,
                            "bios": "bios",
                            "dtb": "dtb",
                            "extra_args": " ".join(arguments),
                        },
                        # The first boot of a slot creates dropbear's host keys,
                        # which takes a while under TCG, before the first
                        # connection is accepted.
                        "SSHDriver": {"connection_timeout": 120.0},
                    },
                },
            },
            "images": {
                "bios": str(directory / FIRMWARE_FILE),
                "dtb": str(directory / DTB_FILE),
            },
            "tools": {"qemu": QEMU},
        }


def manifest_flags(build: Path, key: str) -> list[str]:
    """Return the compiler flags the manifest of ``build`` records under ``key``."""
    manifest = json.loads((build / MANIFEST_FILE).read_text())
    return str(manifest[key]).split()


def sha256(path: Path) -> str:
    """SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def run(*command: str) -> str:
    """Run a tool of the test environment, fail on a non-zero exit, return stdout."""
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def boot_files(disk: Path, partition: int, names: tuple[str, ...], output: Path) -> None:
    """Copy files of a boot partition (ext4) of a raw disk into ``output``."""
    with disk.open("rb") as raw:
        boot = read_mbr(raw.read(SECTOR)).partition(partition)
        raw.seek(boot.start)
        filesystem = output / "boot.ext4"
        filesystem.write_bytes(raw.read(boot.size))
    for name in names:
        file = output / name
        # debugfs exits 0 even when the file is missing; check the result instead.
        run("debugfs", "-R", f"dump /{name} {file}", str(filesystem))
        if not file.is_file() or file.stat().st_size == 0:
            msg = f"{name} not found on partition {partition}"
            raise FileNotFoundError(msg)
    filesystem.unlink()


def read_fit(path: Path) -> Fit:
    """List a FIT image file."""
    return parse_fit(run("dumpimage", "-l", str(path)))


def extract_fit_image(path: Path, image: FitNode, output: Path) -> None:
    """Write one image of a FIT file to ``output``, as stored (still compressed)."""
    run("dumpimage", "-T", "flat_dt", "-p", str(image.index), "-o", str(output), str(path))


@dataclass(frozen=True, slots=True)
class Build:
    """The outputs of one build that the emulator boots, as its manifest lists them."""

    directory: Path
    board: Board
    image: Path
    firmware: Path

    @classmethod
    def read(cls, directory: Path) -> Self:
        """Find the board, the factory image and the firmware; check both against the manifest."""
        images = sorted(directory.glob(FACTORY_IMAGE))
        if len(images) != 1:
            msg = f"expected one {FACTORY_IMAGE} in {directory}, found {len(images)}"
            raise SystemExit(msg)
        manifest = json.loads((directory / MANIFEST_FILE).read_text())
        build = cls(directory, load(manifest["board"]), images[0], directory / FIRMWARE)
        for path in (build.image, build.firmware):
            name = path.relative_to(directory).as_posix()
            if sha256(path) != manifest["files"].get(name):
                msg = f"{name} does not match {directory / MANIFEST_FILE}"
                raise SystemExit(msg)
        return build


def prepare(build: Build, root: Path) -> Path:
    """Build (or reuse) the emulator directory for a build and return it."""
    machine = Machine(build.board)
    image_sha256, firmware_sha256 = sha256(build.image), sha256(build.firmware)
    identity = f"{image_sha256} {firmware_sha256} {build.board.model_dump_json()}"
    directory = root / hashlib.sha256(identity.encode()).hexdigest()[:16]
    if not (directory / SOURCE_FILE).is_file():
        root.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=f"{directory.name}.", dir=root))
        disk_file, disk = work / DISK_FILE, BOOT_DISKS[build.board.boot_disk]
        with build.image.open("rb") as source, disk_file.open("wb") as target:
            gunzip_first_member(source, target)
        if disk_file.stat().st_size > disk.size:
            msg = f"{build.image.name} is larger than a {disk.size >> 30} GiB {disk.device}"
            raise SystemExit(msg)
        os.truncate(disk_file, disk.size)
        shutil.copyfile(build.firmware, work / FIRMWARE_FILE)

        dtb = work / DTB_FILE
        machine.dump_dtb(dtb, work / FIRMWARE_FILE)
        run("fdtput", "-t", "s", str(dtb), "/", "compatible", build.board.board_name)
        run("fdtput", "-t", "s", str(dtb), "/", "model", build.board.model)
        # Each core's capacity as on the SoC, so that the kernel knows the big cores.
        cpus = sorted(
            (node for node in run("fdtget", "-l", str(dtb), "/cpus").split() if "@" in node),
            key=lambda node: int(node.partition("@")[2], 16),
        )
        for node, capacity in zip(cpus, build.board.soc.cores, strict=True):
            run("fdtput", "-t", "u", str(dtb), f"/cpus/{node}", "capacity-dmips-mhz", str(capacity))

        source = {
            "build": str(build.directory),
            "board": build.board.id,
            "image": str(build.image),
            "image_sha256": image_sha256,
            "firmware": str(build.firmware),
            "firmware_sha256": firmware_sha256,
        }
        (work / SOURCE_FILE).write_text(json.dumps(source, indent=2) + "\n")
        shutil.rmtree(directory, ignore_errors=True)
        work.rename(directory)
    description = machine.description(directory)
    (directory / TARGET_FILE).write_text(yaml.safe_dump(description, sort_keys=False))
    return directory


def _current(source: dict[str, str]) -> bool:
    """Return whether the build an emulator directory was made from still has those files."""
    build = Path(source["build"])
    try:
        files = json.loads((build / MANIFEST_FILE).read_text())["files"]
    except FileNotFoundError:
        return False
    return all(
        files.get(Path(source[kind]).relative_to(build).as_posix()) == source[f"{kind}_sha256"]
        for kind in ("image", "firmware")
    )


def prune(root: Path) -> None:
    """Remove the emulator directories of builds that have changed or gone since."""
    for source in root.glob(f"*/{SOURCE_FILE}"):
        if not _current(json.loads(source.read_text())):
            shutil.rmtree(source.parent)


def main(argv: list[str] | None = None) -> int:
    """emu-prepare: print the emulator directory prepared for the outputs of a build."""
    parser = argparse.ArgumentParser(prog="emu-prepare", description=main.__doc__)
    parser.add_argument("build", type=Path, help="the output directory of a build")
    parser.add_argument("root", type=Path, help="directory that holds prepared emulators")
    args = parser.parse_args(argv)
    prune(args.root)
    directory = prepare(Build.read(args.build), args.root)
    sys.stdout.write(f"{directory}\n")
    return 0


class Console:
    """Drain the serial console for as long as the machine runs.

    QEMU's PL011 writes one byte at a time, and on the labgrid socket every byte
    takes a whole socket-buffer slot, so an unread console stalls the guest within
    a few hundred bytes. A thread reads it continuously into memory and a log file;
    tests wait for console output against that record.
    """

    def __init__(self, qemu: QEMUDriver, log: Path) -> None:
        """Read ``qemu``'s console into memory and append it to ``log``."""
        self._qemu = qemu
        self._log = log
        self._data = bytearray()
        self._changed = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start draining; call after the machine is powered on."""
        self._stop.clear()
        self._thread = threading.Thread(target=self._drain, name="console", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop draining; call before the machine is powered off."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _drain(self) -> None:
        with self._log.open("ab") as log:
            while not self._stop.is_set():
                try:
                    # _read is the console primitive every labgrid console driver
                    # implements; read() would record each call as a test step.
                    chunk = self._qemu._read(size=4096, timeout=0.2)  # noqa: SLF001
                except TIMEOUT:
                    continue
                log.write(chunk)
                log.flush()
                with self._changed:
                    self._data += chunk
                    self._changed.notify_all()

    def mark(self) -> int:
        """Return the current end of the record; wait_for() can search from here."""
        with self._changed:
            return len(self._data)

    def text(self, since: int = 0) -> str:
        """Return the console output after ``since``, as text."""
        with self._changed:
            return self._data[since:].decode(errors="replace")

    def wait_for(self, pattern: str, *, since: int, timeout: float) -> str:
        """Wait until ``pattern`` (a regular expression) appears after ``since``."""
        regex = re.compile(pattern.encode())
        deadline = time.monotonic() + timeout
        with self._changed:
            while (match := regex.search(self._data, since)) is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    msg = f"the console never showed {pattern!r}"
                    raise TimeoutError(msg)
                self._changed.wait(remaining)
            return match.group().decode(errors="replace")


class Emulator:
    """Power, disk snapshots and serial console of the emulated board."""

    SNAPSHOT = "booted"

    def __init__(self, target: Target, directory: Path, console_log: Path) -> None:
        """Bind to the QEMUDriver of ``target``; ``directory`` is the prepared one."""
        self.target = target
        self.qemu: QEMUDriver = target.get_driver("QEMUDriver", activate=False)
        self.console = Console(self.qemu, console_log)
        self.disk = directory / DISK_FILE
        self.overlay = directory / OVERLAY_FILE

    def reset_disk(self) -> None:
        """Start from the shipped disk again: a fresh copy-on-write overlay."""
        run(
            "qemu-img",
            *("create", "-q", "-f", "qcow2"),
            *("-b", str(self.disk), "-F", "raw", str(self.overlay)),
        )

    def power_on(self) -> None:
        """Start the machine and drain its console."""
        self.target.activate(self.qemu)
        self.qemu.on()
        self.console.start()

    def power_cut(self) -> None:
        """Kill the machine without any shutdown; the disk keeps what was written."""
        self.console.stop()
        self.qemu.off()

    def _monitor(self, command_line: str) -> None:
        # HMP reports failures as output text, not as a QMP error.
        output = str(
            self.qemu.monitor_command("human-monitor-command", {"command-line": command_line})
        )
        if output.strip():
            msg = f"{command_line}: {output.strip()}"
            raise RuntimeError(msg)

    def save(self) -> None:
        """Snapshot memory and disk of the running machine."""
        self._monitor(f"savevm {self.SNAPSHOT}")

    def restore(self) -> None:
        """Return to the snapshot taken by save()."""
        self._monitor(f"loadvm {self.SNAPSHOT}")

    def throttle_writes(self, bps: int) -> None:
        """Limit writes to the boot disk to ``bps`` bytes per second until the power is cut."""
        limits = dict.fromkeys(("bps", "bps_rd", "iops", "iops_rd", "iops_wr"), 0)
        self.qemu.monitor_command(
            "block_set_io_throttle", {"id": BOOT_DISK_ID, "bps_wr": bps, **limits}
        )

    def send_keys(self, text: str) -> None:
        """Type on the serial console."""
        self.qemu.write(text.encode())

    def plug_disk(self, name: str, image: Path, port: int) -> None:
        """Plug ``image`` in as a USB SSD (UAS, as the boards' data disks) on xHCI port ``port``.

        The disk's SCSI product name is ``name``, which the guest shows as its
        model. The machine's snapshot holds no such disk (a raw image takes no
        internal snapshot), so a disk must be unplugged before the machine is
        restored.
        """
        file = {"driver": "file", "filename": str(image)}
        self.qemu.monitor_command(
            "blockdev-add", {"driver": "raw", "node-name": name, "file": file}
        )
        uas = {"driver": "usb-uas", "id": f"{name}-uas", "bus": "xhci.0", "port": str(port)}
        self.qemu.monitor_command("device_add", uas)
        disk = {
            "driver": "scsi-hd",
            "id": f"{name}-hd",
            "bus": f"{name}-uas.0",
            "drive": name,
            "product": name,
        }
        self.qemu.monitor_command("device_add", disk)
        # A hot-plugged usb-uas waits for its disk: only now it appears on the port.
        self.qemu.monitor_command(
            "qom-set",
            {"path": f"/machine/peripheral/{name}-uas", "property": "attached", "value": True},
        )

    def unplug_disk(self, name: str) -> None:
        """Pull a disk plug_disk() plugged in."""
        self.qemu.monitor_command("device_del", {"id": f"{name}-uas"})
        # The drive is free once the disk device has let it go, which QEMU
        # finishes a little after the device is gone.
        deadline = time.monotonic() + UNPLUG_TIMEOUT
        while self._drive_in_use(name):
            if time.monotonic() > deadline:
                msg = f"{name} was not unplugged"
                raise TimeoutError(msg)
            time.sleep(0.2)
        self.qemu.monitor_command("blockdev-del", {"node-name": name})

    def _drive_in_use(self, name: str) -> bool:
        """Return whether a device's block backend still holds the drive ``name``."""
        blocks = self.qemu.monitor_command("query-block")
        return any(block.get("inserted", {}).get("node-name") == name for block in blocks)


if __name__ == "__main__":
    sys.exit(main())
