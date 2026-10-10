"""The emulated router under test (design D13).

Commands run over SSH: the runner reaches the router's LAN address from inside the
sandbox. ``reset`` returns the emulator to its post-boot snapshot.
"""

import re
import shlex
import socket
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import TYPE_CHECKING, cast

from labgrid.driver import ExecutionError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from labgrid import Target
    from labgrid.driver import SSHDriver

    from wrt_tests.device.emu import Emulator

SSH_PORT = 22
# Terminal control in a login session's output: CSI sequences and carriage returns.
_TERMINAL_CONTROL = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\r")
BOOT_TIMEOUT = 600.0
READY_MARK = "- init complete -"
# The kernel's last words before the machine restarts.
RESTART_MARK = "reboot: Restarting system"
BOOT_ID = "cat /proc/sys/kernel/random/boot_id"
# A connection the router stopped answering: labgrid says so before it runs a
# command, and ssh exits with this status.
DEAD_CONNECTION = "Keepalive no longer running"
SSH_FAILED = 255
# How long a new connection is tried: the emulator stops answering while the
# disk it runs from catches up with a burst of writes.
RECONNECT_TIMEOUT = 60.0
# How long an interactive login may take: zsh's first start after a boot builds
# its completion dump in /tmp, 21 to 26 s under TCG on an idle host and several
# times that on a busy one (2026-10-03); later logins take 7 to 9 s.
LOGIN_TIMEOUT = 180.0
# The serial console's shell answers a knock with this line, and a script's end
# with that one; the typed commands, which the console echoes, hold neither.
CONSOLE_READY = "console-ready"
CONSOLE_END = "console-end"
CONSOLE_KNOCK = 15.0


def _check(deadline: float, message: str) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError(message)


def _port_open(address: str, port: int) -> bool:
    try:
        with socket.create_connection((address, port), timeout=2):
            return True
    except OSError:
        return False


class Router:
    """Run commands on the router and wait for it."""

    def __init__(self, target: Target, emulator: Emulator, key: Path) -> None:
        """Bind to the SSHDriver of ``target`` on ``emulator``; log in with ``key``.

        root has no password on a fresh router, and dropbear lets it in without
        one; the key logs in once it has one.
        """
        self.target = target
        self.emulator = emulator
        self.key = key
        self.ssh: SSHDriver = target.get_driver("SSHDriver", activate=False)
        self.ssh.keyfile = str(key)
        self.address = str(target.get_resource("NetworkService").address)

    def _connected(self) -> SSHDriver:
        self.target.activate(self.ssh)
        return self.ssh

    def disconnect(self) -> None:
        """Close the SSH connection, e.g. before the router's state jumps."""
        self.target.deactivate(self.ssh)

    def _run(self, command: str, timeout: float) -> tuple[list[str], list[str], int]:
        """Run ``command`` over the SSH connection, a new one if the old one has died.

        labgrid refuses a command on a dead connection before running it, so
        running it on a new one runs it once.
        """
        try:
            result = self._connected().run(command, timeout=timeout)
        except ExecutionError as error:
            if DEAD_CONNECTION not in str(error):
                raise
            self.disconnect()
            result = self._connected().run(command, timeout=timeout)
        return cast("tuple[list[str], list[str], int]", result)

    def run(self, command: str, *, timeout: float = 60) -> str:
        """Run a shell command on the router, fail on a non-zero exit, return stdout."""
        stdout, stderr, code = self._run(command, timeout)
        if code != 0:
            msg = f"{command!r} exited {code}: {'\n'.join(stderr)}"
            raise AssertionError(msg)
        return "\n".join(map(str, stdout))

    def poll(self, command: str, *, timeout: float = 30) -> str | None:
        """Run a shell command if the router answers; return stdout, or None if not or it failed.

        For states the router passes through while it reboots, when SSH comes
        and goes, or hangs while the old system goes down.
        """
        try:
            stdout, _, code = self._connected().run(command, timeout=timeout)
        # labgrid raises a bare Exception for a connection that never came up.
        except Exception:  # noqa: BLE001
            self.disconnect()
            return None
        if code != 0:
            self.disconnect()
            return None
        return "\n".join(map(str, stdout))

    def returncode(self, command: str, *, timeout: float = 60) -> int:
        """Run a shell command on the router and return only its exit status."""
        _, _, code = self._run(command, timeout)
        return int(code)

    def _ssh(self, *options: str) -> list[str]:
        return ["ssh", *options, "-o", "BatchMode=yes", "-i", str(self.key), f"root@{self.address}"]

    def login(self, script: str, *, timeout: float = LOGIN_TIMEOUT) -> str:
        """Log in interactively (with a terminal) and type ``script``; return the session output.

        This is a real login shell, unlike run(), so /etc/profile and the zsh
        hand-over apply. The script should end with ``exit``.
        """
        with subprocess.Popen(
            self._ssh("-tt"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        ) as session:
            stdin, stdout = session.stdin, session.stdout
            if stdin is None or stdout is None:
                msg = "ssh has no pipes"
                raise RuntimeError(msg)
            stdin.write(script)
            stdin.flush()
            # Keep stdin open: at end of input ssh would end the session before the
            # shell has read the script. The script's own exit ends it.
            session.wait(timeout=timeout)
            output = stdout.read()
        return _TERMINAL_CONTROL.sub("", output)

    def console(self, script: str, *, timeout: float = LOGIN_TIMEOUT) -> str:
        """Run ``script`` in the serial console's shell; return what it printed.

        For a router that ssh cannot reach. Enter activates the console's shell,
        whose login takes a while, so a knock repeats until the shell answers. A
        console that never answers, or never finishes, is said so after what it
        showed meanwhile.
        """
        console = self.emulator.console
        since = console.mark()
        deadline = time.monotonic() + timeout

        def shows(line: str, mark: int, limit: float) -> bool:
            remaining = min(limit, deadline - time.monotonic())
            try:
                console.wait_for(rf"(?m)^{line}\r?$", since=mark, timeout=max(remaining, 0.0))
            except TimeoutError:
                return False
            return True

        self.emulator.send_keys("\n")
        while True:
            mark = console.mark()
            self.emulator.send_keys(f"echo '{CONSOLE_READY[:4]}''{CONSOLE_READY[4:]}'\n")
            if shows(CONSOLE_READY, mark, CONSOLE_KNOCK):
                break
            if time.monotonic() >= deadline:
                return f"{console.text(since)}\n(no shell answered on the console)"
        mark = console.mark()
        self.emulator.send_keys(f"{script}; echo '{CONSOLE_END[:4]}''{CONSOLE_END[4:]}'\n")
        if not shows(CONSOLE_END, mark, timeout):
            return f"{console.text(since)}\n(the console did not finish the script)"
        return _TERMINAL_CONTROL.sub("", console.text(mark))

    def put(self, local: Path, remote: str) -> None:
        """Copy a local file to the router (over ssh; dropbear has no sftp server).

        A connection the router does not take is tried again for a while.
        """
        deadline = time.monotonic() + RECONNECT_TIMEOUT
        while True:
            with local.open("rb") as source:
                copy = subprocess.run(
                    [*self._ssh(), f"cat > {shlex.quote(remote)}"],
                    stdin=source,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=600,
                )
            if copy.returncode == 0:
                return
            if copy.returncode != SSH_FAILED or time.monotonic() > deadline:
                failure = subprocess.CalledProcessError(copy.returncode, copy.args)
                failure.add_note(copy.stderr.decode(errors="replace").strip())
                raise failure
            time.sleep(2)

    def wait_ssh(self, timeout: float = BOOT_TIMEOUT) -> None:
        """Wait until the router answers on SSH (in failsafe mode, too)."""
        deadline = time.monotonic() + timeout
        self.disconnect()
        while not _port_open(self.address, SSH_PORT):
            _check(deadline, f"{self.address}:{SSH_PORT} never opened")
            time.sleep(2)

    def wait_ready(self, timeout: float = BOOT_TIMEOUT) -> None:
        """Wait until SSH answers and procd has run every init script; set the clock."""
        deadline = time.monotonic() + timeout
        self.wait_ssh(timeout)
        # procd logs through ulog, which writes to logd (not the kernel log) once
        # logd runs, as it does long before init completes.
        while self.returncode(f"logread | grep -qF -- '{READY_MARK}'") != 0:
            _check(deadline, "procd never reported init complete")
            time.sleep(2)
        self.set_clock()

    def set_clock(self) -> None:
        """Set the router's clock to the runner's, as NTP does on a router in service.

        The emulated internet has no time server: a router boots with the time
        of its newest file in /etc, and a restored snapshot rewinds the clock to
        when it was taken. What is signed now (a release's certificate) is valid
        from now on.
        """
        self.run(f"date -s @{int(time.time())} >/dev/null")

    def http(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
        timeout: float = 30,
    ) -> tuple[int, str]:
        """GET ``path`` (POST ``data``) from the router's web server; return status and body."""
        request = urllib.request.Request(
            f"http://{self.address}{path}", headers=headers or {}, data=data
        )
        try:
            # Always http://<router address>; no other scheme is ever built.
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return int(response.status), str(response.read().decode(errors="replace"))
        except urllib.error.HTTPError as error:
            return int(error.code), str(error.read().decode(errors="replace"))

    def detach(self, command: str) -> None:
        """Start a command that outlives the connection (reboot, sysupgrade, ...)."""
        self.run(f"({command}) >/dev/null 2>&1 </dev/null &")

    def boot_id(self) -> str:
        """Return the kernel's boot ID, which changes with every boot."""
        return self.run(BOOT_ID)

    def wait_rebooted(self, previous_boot: str, timeout: float = BOOT_TIMEOUT) -> None:
        """Wait until the router has booted again after ``previous_boot`` and is ready.

        The old system may still answer while it shuts down, and the reboot may
        cut or hang the connection in the middle of a command; each only means
        waiting on. Only a new boot ID is the new system: waiting for it to be
        ready, which sets its clock, starts then, never on the old one.
        """
        deadline = time.monotonic() + timeout
        while (boot := self.poll(BOOT_ID)) is None or boot == previous_boot:
            _check(deadline, "the router never rebooted")
            time.sleep(2)
        self.wait_ready(deadline - time.monotonic())

    def reboot(
        self, command: str = "reboot", *, while_off: Callable[[], object] | None = None
    ) -> None:
        """Run ``command`` (which must end in a reboot) and wait until the router is back.

        ``while_off`` runs between the end of the old system and the next boot:
        hardware changed then is changed with the power off, after the old
        system has written out and unmounted everything.
        """
        previous_boot = self.boot_id()
        mark = self.emulator.console.mark()
        self.detach(f"sleep 1; {command}")
        if while_off is not None:
            self.emulator.console.wait_for(RESTART_MARK, since=mark, timeout=BOOT_TIMEOUT)
            while_off()
        self.wait_rebooted(previous_boot)

    @contextmanager
    def moved_to(self, address: str) -> Iterator[None]:
        """Reach the router at another LAN address inside the block."""
        service = self.target.get_resource("NetworkService")
        original = self.address
        self.disconnect()
        service.address = self.address = address
        try:
            yield
        finally:
            self.disconnect()
            service.address = self.address = original

    def reset(self) -> None:
        """Return to the state right after boot (the emulator's snapshot), at the time of now."""
        self.disconnect()
        self.emulator.restore()
        self.set_clock()
