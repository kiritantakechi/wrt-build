"""The rootless network sandbox around the emulator (design D14).

``scripts/test.sh`` starts pytest inside ``unshare --user --map-root-user --net
--mount``, so everything here runs as root of a private user namespace and changes
nothing on the host. The topology is data: bridges with the emulator's tap and the
test runner's address, and network namespaces joined to a bridge through a veth
pair, each with a static address or a DHCP client and optional daemons. Later
changes add namespaces (PPPoE server, internet probes, ...) by extending
``TOPOLOGY``; nothing else needs to change.

A namespace is held by a ``sleep`` process started with ``unshare --net``;
commands enter it with ``nsenter``. No named namespaces, so no /run/netns and no
real root are needed.
"""

import subprocess
import time
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Self, override

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

UDHCPC_SCRIPT = Path(__file__).with_name("udhcpc.sh")
RUNNER_ADDRESS = "10.0.0.2"
DAEMON_SETTLE = 0.5


@dataclass(frozen=True, slots=True)
class Bridge:
    """A bridge in the sandbox; ``tap`` is the emulator's port on it."""

    name: str
    tap: str
    address: str | None = None


@dataclass(frozen=True, slots=True)
class Namespace:
    """A network namespace on a bridge: static ``address``, or DHCP when it is None.

    ``daemons`` are command lines started inside the namespace; ``{workdir}`` in an
    argument is replaced with a private directory of that namespace.
    """

    name: str
    bridge: str
    address: str | None = None
    daemons: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class Topology:
    """Everything the sandbox contains."""

    bridges: tuple[Bridge, ...]
    namespaces: tuple[Namespace, ...]


TOPOLOGY = Topology(
    bridges=(
        Bridge("br-lan", tap="emu-lan", address=f"{RUNNER_ADDRESS}/24"),
        Bridge("br-wan", tap="emu-wan"),
    ),
    namespaces=(
        Namespace("client-a", bridge="br-lan"),
        Namespace(
            "isp",
            bridge="br-wan",
            address="192.0.2.1/24",
            daemons=(
                (
                    "dnsmasq",
                    "--keep-in-foreground",
                    "--conf-file=/dev/null",
                    "--port=0",
                    # Empty user and group: keep the sandbox's identity; setgroups
                    # is not allowed in a user namespace.
                    "--user=",
                    "--group=",
                    "--log-facility=-",
                    "--interface=eth0",
                    "--bind-interfaces",
                    "--dhcp-range=192.0.2.100,192.0.2.199,1h",
                    "--dhcp-leasefile={workdir}/leases",
                    "--pid-file=",
                ),
            ),
        ),
    ),
)


def ip(*args: str) -> str:
    """Run ``ip`` in the sandbox's own namespace and return its output."""
    return subprocess.run(["ip", *args], check=True, capture_output=True, text=True).stdout


class Netns(AbstractContextManager["Netns"]):
    """A network namespace held open by a sleeping process."""

    def __init__(self, name: str) -> None:
        """Create the namespace; it lives until the context exits."""
        self.name = name
        own = Path("/proc/self/ns/net").stat().st_ino
        self._holder = subprocess.Popen(["unshare", "--net", "--", "sleep", "infinity"])
        deadline = time.monotonic() + 5
        while Path(self.path).stat().st_ino == own:
            if time.monotonic() > deadline:
                msg = f"namespace {name} did not come up"
                raise TimeoutError(msg)
            time.sleep(0.01)

    @property
    def path(self) -> str:
        """The namespace file of the holder process."""
        return f"/proc/{self._holder.pid}/ns/net"

    @property
    def pid(self) -> int:
        """The holder process; ``ip link set ... netns <pid>`` moves links here."""
        return self._holder.pid

    def argv(self, *command: str) -> list[str]:
        """Prefix a command line so that it runs inside this namespace."""
        return ["nsenter", f"--net={self.path}", "--", *command]

    def run(self, *command: str, timeout: float = 30) -> str:
        """Run a command inside the namespace and return its output."""
        result = subprocess.run(
            self.argv(*command), check=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout

    def spawn(self, *command: str) -> subprocess.Popen[bytes]:
        """Start a long-running command inside the namespace."""
        return subprocess.Popen(self.argv(*command), stdin=subprocess.DEVNULL)

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stop the holder; the namespace disappears with it."""
        self._holder.kill()
        self._holder.wait()


class Network(AbstractContextManager["Network"]):
    """The sandbox topology, built on entry and torn down on exit."""

    def __init__(self, topology: Topology, workdir: Path) -> None:
        """Remember what to build; ``workdir`` holds the daemons' files."""
        self.topology = topology
        self.workdir = workdir
        self._stack = ExitStack()
        self._namespaces: dict[str, Netns] = {}

    def __getitem__(self, name: str) -> Netns:
        """Return a namespace of the topology by name."""
        return self._namespaces[name]

    @override
    def __enter__(self) -> Self:
        """Create bridges, taps and namespaces, then start DHCP clients and daemons."""
        ip("link", "set", "lo", "up")
        for bridge in self.topology.bridges:
            ip("link", "add", "name", bridge.name, "type", "bridge")
            ip("tuntap", "add", "dev", bridge.tap, "mode", "tap")
            ip("link", "set", bridge.tap, "master", bridge.name, "up")
            ip("link", "set", bridge.name, "up")
            if bridge.address:
                ip("addr", "add", bridge.address, "dev", bridge.name)
        for namespace in self.topology.namespaces:
            self._add(namespace)
        return self

    def _add(self, namespace: Namespace) -> None:
        netns = self._stack.enter_context(Netns(namespace.name))
        self._namespaces[namespace.name] = netns
        port = f"v-{namespace.name}"
        ip("link", "add", port, "type", "veth", "peer", "name", "eth0", "netns", str(netns.pid))
        ip("link", "set", port, "master", namespace.bridge, "up")
        netns.run("ip", "link", "set", "lo", "up")
        netns.run("ip", "link", "set", "eth0", "up")
        if namespace.address:
            netns.run("ip", "addr", "add", namespace.address, "dev", "eth0")
        else:
            self._daemon(netns, ("udhcpc", "-f", "-i", "eth0", "-s", str(UDHCPC_SCRIPT), "-A", "3"))
        workdir = self.workdir / namespace.name
        workdir.mkdir(parents=True, exist_ok=True)
        for daemon in namespace.daemons:
            self._daemon(netns, tuple(arg.format(workdir=workdir) for arg in daemon))

    def _daemon(self, netns: Netns, command: Sequence[str]) -> None:
        process = netns.spawn(*command)
        self._stack.callback(process.wait)
        self._stack.callback(process.terminate)
        try:
            code = process.wait(timeout=DAEMON_SETTLE)
        except subprocess.TimeoutExpired:
            return
        msg = f"{netns.name}: {command[0]} exited with {code} right after starting"
        raise RuntimeError(msg)

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stop daemons and namespaces; links vanish with the sandbox."""
        self._stack.close()
