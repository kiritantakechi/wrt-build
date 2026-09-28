"""The emulated R4S (design D14, r4s-ab-rollback D7): its files and driving it at run time.

``emu-prepare`` turns the outputs of a build into what the emulator boots: the
factory image as a raw SD card, which every test run overlays with copy-on-write;
the emulator's U-Boot as firmware; and an R4S-identity device tree, which U-Boot
hands on to the kernel it starts from the slot. The machine parameters come from
the labgrid target description, so the device tree always matches the machine
that boots it. The output directory is keyed by the image and firmware and reused.

``Emulator`` gives the tests power, disk snapshots and the serial console.
"""

import argparse
import hashlib
import json
import os
import re
import shlex
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

from wrt_tests.image import SECTOR, Fit, FitNode, gunzip_first_member, parse_fit, read_mbr

if TYPE_CHECKING:
    from labgrid import Target
    from labgrid.driver import QEMUDriver

TARGETS_DIR = Path(__file__).resolve().parent.parent / "targets"
BOARD_COMPATIBLE = "friendlyarm,nanopi-r4s"
BOARD_MODEL = "FriendlyElec NanoPi R4S"
MANIFEST_FILE = "manifest.json"
FACTORY_IMAGE = "targets/*-factory.img.gz"
FIRMWARE = "u-boot-qemu.bin"
SOURCE_FILE = "source.json"
# A 4 GB card: QEMU wants SD cards sized in powers of two.
SD_CARD_SIZE = 4 << 30


class _TemplateLoader(yaml.SafeLoader):
    """Loads labgrid descriptions, keeping ``!template`` scalars unexpanded."""


_TemplateLoader.add_constructor("!template", lambda loader, node: loader.construct_scalar(node))


@dataclass(frozen=True, slots=True)
class Machine:
    """The QEMU machine of the emulation target, as far as the device tree depends on it."""

    qemu: str
    machine: str
    cpu: str
    memory: str
    smp: str

    @classmethod
    def from_description(cls, path: Path) -> Self:
        """Read the QEMUDriver of ``targets.main`` in a labgrid target description."""
        # _TemplateLoader is a SafeLoader that only adds the !template tag.
        description: dict[str, Any] = yaml.load(path.read_text(), Loader=_TemplateLoader)  # noqa: S506
        driver = description["targets"]["main"]["drivers"]["QEMUDriver"]
        extra = shlex.split(driver["extra_args"])
        return cls(
            qemu=description["tools"][driver["qemu_bin"]],
            machine=driver["machine"],
            cpu=driver["cpu"],
            memory=driver["memory"],
            smp=extra[extra.index("-smp") + 1],
        )

    def dump_dtb(self, output: Path, firmware: Path) -> None:
        """Write the device tree QEMU generates for this machine running ``firmware``.

        The firmware belongs to the machine: with one, QEMU replaces the PL061 GPIO
        with an ACPI event device, and a device tree without it would describe a
        device the kernel faults on.
        """
        subprocess.run(
            [
                self.qemu,
                *("-machine", f"{self.machine},dumpdtb={output}"),
                *("-cpu", self.cpu, "-m", self.memory, "-smp", self.smp),
                *("-bios", str(firmware)),
                "-nographic",
            ],
            check=True,
            capture_output=True,
        )


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
    image: Path
    firmware: Path

    @classmethod
    def read(cls, directory: Path) -> Self:
        """Find the factory image and the firmware, and check both against the manifest."""
        images = sorted(directory.glob(FACTORY_IMAGE))
        if len(images) != 1:
            msg = f"expected one {FACTORY_IMAGE} in {directory}, found {len(images)}"
            raise SystemExit(msg)
        build = cls(directory, images[0], directory / FIRMWARE)
        files = json.loads((directory / MANIFEST_FILE).read_text())["files"]
        for path in (build.image, build.firmware):
            name = path.relative_to(directory).as_posix()
            if sha256(path) != files.get(name):
                msg = f"{name} does not match {directory / MANIFEST_FILE}"
                raise SystemExit(msg)
        return build


def prepare(build: Build, root: Path, machine: Machine) -> Path:
    """Build (or reuse) the emulator directory for a build and return it."""
    image_sha256, firmware_sha256 = sha256(build.image), sha256(build.firmware)
    key = hashlib.sha256(f"{image_sha256} {firmware_sha256}".encode()).hexdigest()
    directory = root / key[:16]
    if (directory / SOURCE_FILE).is_file():
        return directory

    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{directory.name}.", dir=root))
    disk_file = work / "disk.raw"
    with build.image.open("rb") as source, disk_file.open("wb") as target:
        gunzip_first_member(source, target)
    if disk_file.stat().st_size > SD_CARD_SIZE:
        msg = f"{build.image.name} is larger than a {SD_CARD_SIZE >> 30} GiB card"
        raise SystemExit(msg)
    os.truncate(disk_file, SD_CARD_SIZE)
    shutil.copyfile(build.firmware, work / "u-boot.bin")

    machine.dump_dtb(work / "r4s.dtb", work / "u-boot.bin")
    run("fdtput", "-t", "s", str(work / "r4s.dtb"), "/", "compatible", BOARD_COMPATIBLE)
    run("fdtput", "-t", "s", str(work / "r4s.dtb"), "/", "model", BOARD_MODEL)

    source = {
        "build": str(build.directory),
        "image": str(build.image),
        "image_sha256": image_sha256,
        "firmware": str(build.firmware),
        "firmware_sha256": firmware_sha256,
    }
    (work / SOURCE_FILE).write_text(json.dumps(source, indent=2) + "\n")
    shutil.rmtree(directory, ignore_errors=True)
    work.rename(directory)
    return directory


def main(argv: list[str] | None = None) -> int:
    """emu-prepare: print the emulator directory prepared for the outputs of a build."""
    parser = argparse.ArgumentParser(prog="emu-prepare", description=main.__doc__)
    parser.add_argument("build", type=Path, help="the output directory of a build")
    parser.add_argument("root", type=Path, help="directory that holds prepared emulators")
    parser.add_argument(
        "--target",
        type=Path,
        default=TARGETS_DIR / "emulation.yaml",
        help="labgrid description of the emulation target",
    )
    args = parser.parse_args(argv)
    machine = Machine.from_description(args.target)
    directory = prepare(Build.read(args.build), args.root, machine)
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
    """Power, disk snapshots and serial console of the emulated R4S."""

    SNAPSHOT = "booted"

    def __init__(self, target: Target, directory: Path, console_log: Path) -> None:
        """Bind to the QEMUDriver of ``target``; ``directory`` is the prepared one."""
        self.target = target
        self.qemu: QEMUDriver = target.get_driver("QEMUDriver", activate=False)
        self.console = Console(self.qemu, console_log)
        self.disk = directory / "disk.raw"
        self.overlay = directory / "overlay.qcow2"

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
        """Limit writes to the SD card to ``bps`` bytes per second until the power is cut."""
        limits = dict.fromkeys(("bps", "bps_rd", "iops", "iops_rd", "iops_wr"), 0)
        self.qemu.monitor_command("block_set_io_throttle", {"id": "card", "bps_wr": bps, **limits})

    def send_keys(self, text: str) -> None:
        """Type on the serial console."""
        self.qemu.write(text.encode())


if __name__ == "__main__":
    sys.exit(main())
