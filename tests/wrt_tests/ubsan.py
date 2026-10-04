"""Undefined behavior that traps in a ``ubsan`` build (toolchain-o3 D5).

In the ``ubsan`` profile, every target package is built with UBSan in trap mode:
undefined behavior executes ``brk #0x3e8``, and the kernel kills the process with
SIGTRAP. That image turns on the kernel's report of unhandled signals
(``debug.exception-trace``, which wrt-ubsan-probe sets from early boot), so each
trap leaves its process, pid and address in the kernel log, until the emulator
returns to its snapshot.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

import pytest

if TYPE_CHECKING:
    from wrt_tests.router import Router

PROFILE = "ubsan"
PROBE = "wrt-ubsan-probe"
# arm64_show_signal: "<comm>[<pid>]: unhandled exception: ... User debug trap in
# <file>[<start>+<size>]", then the registers, the user-space pc among them.
_UNHANDLED = re.compile(
    r"^(?:\[\s*(?P<time>[0-9.]+)\] )?(?P<process>.+?)\[(?P<pid>[0-9]+)\]: "
    r"unhandled exception: .*User debug trap(?P<where>.*)$"
)
_PC = re.compile(r"^(?:\[\s*[0-9.]+\] )?pc : (?P<pc>[0-9a-f]+)$")
# The registers follow the report within this many lines.
_REGISTERS = 8


@dataclass(frozen=True)
class Trap:
    """A process the kernel killed for a trap: its name, pid and address, and when."""

    process: str
    pid: int
    pc: str
    where: str
    time: str

    @override
    def __str__(self) -> str:
        """Render as ``process[pid] at pc <pc> in <file>[<mapping>]``."""
        return f"{self.process}[{self.pid}] at pc {self.pc}{self.where}"


def parse(log: str) -> list[Trap]:
    """Return the user-space traps the kernel log ``log`` reports."""
    lines = log.splitlines()
    traps = []
    for index, line in enumerate(lines):
        if not (report := _UNHANDLED.match(line)):
            continue
        following = lines[index + 1 : index + 1 + _REGISTERS]
        pcs = [found["pc"] for found in map(_PC.match, following) if found]
        traps.append(
            Trap(
                process=report["process"],
                pid=int(report["pid"]),
                pc=pcs[0] if pcs else "unknown",
                where=report["where"],
                time=report["time"] or "",
            )
        )
    return traps


class Traps:
    """The traps of a ``ubsan`` build's router, each reported once."""

    def __init__(self, router: Router) -> None:
        """Watch the kernel log of ``router``."""
        self._router = router
        self._seen: set[Trap] = set()

    def new(self) -> list[Trap]:
        """Return the traps the kernel log holds that no earlier call returned.

        Nothing when the router does not answer, as after a test that took it down.
        """
        log = self._router.poll("dmesg")
        if log is None:
            return []
        found = [trap for trap in parse(log) if trap not in self._seen]
        self._seen.update(found)
        return found


def report(traps: list[Trap], when: str) -> None:
    """Fail the running test (or fixture) if ``traps`` holds any, naming each."""
    if traps:
        lines = "\n".join(f"  {trap}" for trap in traps)
        pytest.fail(f"undefined behavior trapped {when}:\n{lines}", pytrace=False)
