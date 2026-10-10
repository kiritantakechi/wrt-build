"""A ubsan build's traps, read from the kernel log (wrt_tests.device.ubsan, toolchain-o3 D5)."""

from typing import TYPE_CHECKING, cast

import pytest

from wrt_tests.device.ubsan import Trap, Traps, parse, report

if TYPE_CHECKING:
    from wrt_tests.device.router import Router

# What arm64_show_signal logs for a process killed by a UBSan trap, and for one
# killed by a segmentation fault, with the kernel's time in front.
TRAP = """\
[   41.112233] wrt-ubsan-probe[1234]: unhandled exception: User debug trap in \
wrt-ubsan-probe[aaaab4560000+1000]
[   41.112240] CPU: 1 UID: 0 PID: 1234 Comm: wrt-ubsan-probe Not tainted 6.18.52 #0
[   41.112245] Hardware name: FriendlyElec NanoPi R4S (DT)
[   41.112250] pstate: 60001000 (nZCv daif -PAN -UAO -TCO -DIT +SSBS BTYPE=--)
[   41.112255] pc : 0000aaaab4560654
[   41.112260] lr : 0000ffff9a8b1234
"""
SEGFAULT = """\
[   52.000001] netifd[812]: unhandled exception: DABT (lower EL), ESR 0x0000000092000006, \
level 2 translation fault in netifd[aaaac0000000+30000]
[   52.000010] pc : 0000aaaac0011111
"""


def test_a_trap_names_its_process_and_address() -> None:
    assert parse(TRAP + SEGFAULT) == [
        Trap(
            process="wrt-ubsan-probe",
            pid=1234,
            pc="0000aaaab4560654",
            where=" in wrt-ubsan-probe[aaaab4560000+1000]",
            time="41.112233",
        )
    ]


def test_a_log_without_times_still_names_the_trap() -> None:
    plain = "\n".join(line.split("] ", 1)[1] for line in TRAP.splitlines())
    assert [str(trap) for trap in parse(plain)] == [
        "wrt-ubsan-probe[1234] at pc 0000aaaab4560654 in wrt-ubsan-probe[aaaab4560000+1000]"
    ]


class _Router:
    """A router whose kernel log grows as a test goes on."""

    def __init__(self, *logs: str | None) -> None:
        self.logs = list(logs)

    def poll(self, command: str) -> str | None:
        assert command == "dmesg"
        return self.logs.pop(0)


def test_each_trap_is_reported_once() -> None:
    # A module's tests share the router, and so its kernel log; one that does not
    # answer has nothing to report.
    traps = Traps(cast("Router", _Router("", TRAP, TRAP, None)))
    assert traps.new() == []
    assert [trap.process for trap in traps.new()] == ["wrt-ubsan-probe"]
    assert traps.new() == []
    assert traps.new() == []


def test_a_trap_fails_naming_each_process() -> None:
    report([], "during the test")
    with pytest.raises(pytest.fail.Exception, match=r"wrt-ubsan-probe\[1234\] at pc"):
        report(parse(TRAP), "during the test")
