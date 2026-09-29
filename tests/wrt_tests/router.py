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
from typing import TYPE_CHECKING

from labgrid.driver.exception import ExecutionError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from labgrid import Target
    from labgrid.driver import SSHDriver

    from wrt_tests.emu import Emulator

SSH_PORT = 22
# Terminal control in a login session's output: CSI sequences and carriage returns.
_TERMINAL_CONTROL = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\r")
BOOT_TIMEOUT = 600.0
READY_MARK = "- init complete -"


class Router:
    """Run commands on the router and wait for it."""

    def __init__(self, target: Target, emulator: Emulator) -> None:
        """Bind to the SSHDriver of ``target``; ``emulator`` is the machine it runs on."""
        self.target = target
        self.emulator = emulator
        self.ssh: SSHDriver = target.get_driver("SSHDriver", activate=False)
        self.address = str(target.get_resource("NetworkService").address)

    def _connected(self) -> SSHDriver:
        self.target.activate(self.ssh)
        return self.ssh

    def disconnect(self) -> None:
        """Close the SSH connection, e.g. before the router's state jumps."""
        self.target.deactivate(self.ssh)

    def run(self, command: str, *, timeout: float = 60) -> str:
        """Run a shell command on the router, fail on a non-zero exit, return stdout."""
        stdout, stderr, code = self._connected().run(command, timeout=timeout)
        if code != 0:
            msg = f"{command!r} exited {code}: {'\n'.join(stderr)}"
            raise AssertionError(msg)
        return "\n".join(map(str, stdout))

    def returncode(self, command: str, *, timeout: float = 60) -> int:
        """Run a shell command on the router and return only its exit status."""
        _, _, code = self._connected().run(command, timeout=timeout)
        return int(code)

    def _ssh(self, *options: str) -> list[str]:
        return ["ssh", *options, "-o", "BatchMode=yes", f"root@{self.address}"]

    def login(self, script: str, *, timeout: float = 60) -> str:
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

    def put(self, local: Path, remote: str) -> None:
        """Copy a local file to the router (over ssh; dropbear has no sftp server)."""
        with local.open("rb") as source:
            subprocess.run(
                [*self._ssh(), f"cat > {shlex.quote(remote)}"],
                stdin=source,
                check=True,
                timeout=600,
            )

    def wait_ssh(self, timeout: float = BOOT_TIMEOUT) -> None:
        """Wait until the router answers on SSH (in failsafe mode, too)."""
        deadline = time.monotonic() + timeout
        self.disconnect()
        while not _port_open(self.address, SSH_PORT):
            _check(deadline, f"{self.address}:{SSH_PORT} never opened")
            time.sleep(2)

    def wait_ready(self, timeout: float = BOOT_TIMEOUT) -> None:
        """Wait until SSH answers and procd has run every init script."""
        deadline = time.monotonic() + timeout
        self.wait_ssh(timeout)
        # procd logs through ulog, which writes to logd (not the kernel log) once
        # logd runs, as it does long before init completes.
        while self.returncode(f"logread | grep -qF -- '{READY_MARK}'") != 0:
            _check(deadline, "procd never reported init complete")
            time.sleep(2)

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
        return self.run("cat /proc/sys/kernel/random/boot_id")

    def wait_rebooted(self, previous_boot: str, timeout: float = BOOT_TIMEOUT) -> None:
        """Wait until the router has booted again after ``previous_boot`` and is ready.

        The reboot may cut the connection in the middle of a command; that only
        means waiting on.
        """
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.wait_ready(deadline - time.monotonic())
                if self.boot_id() != previous_boot:
                    return
            except ExecutionError:
                self.disconnect()
            _check(deadline, "the router never rebooted")
            time.sleep(2)

    def reboot(self, command: str = "reboot") -> None:
        """Run ``command`` (which must end in a reboot) and wait until the router is back."""
        previous_boot = self.boot_id()
        self.detach(f"sleep 1; {command}")
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
        """Return to the state right after boot, the emulator's snapshot."""
        self.disconnect()
        self.emulator.restore()


def _port_open(address: str, port: int) -> bool:
    try:
        with socket.create_connection((address, port), timeout=2):
            return True
    except OSError:
        return False


def _check(deadline: float, message: str) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError(message)
