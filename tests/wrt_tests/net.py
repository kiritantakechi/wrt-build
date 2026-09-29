"""The rootless network sandbox around the emulator (design D14).

``scripts/test.sh`` starts pytest inside ``unshare --user --map-root-user --net
--mount``, so everything here runs as root of a private user namespace and changes
nothing on the host. The topology is data: bridges (with the emulator's taps and
the test runner's address), and network namespaces whose ports are veth pairs to
the bridges, each port with static addresses or a DHCP client, plus routes and
daemons. Later changes add namespaces by extending ``TOPOLOGY``.

```
client-a ─┐                                                 ┌─ inet   netprobe, dns, iperf3
client-b ─┼─ br-lan ─ eth1 │ router │ eth0 ─ br-wan ─ isp ─ br-inet ─┤
runner   ─┘ 10.0.0.0/24    │ (QEMU) │  PPPoE        (BRAS)          └─ proxy  socks5 exit
```

A namespace is held by a ``sleep`` process started with ``unshare --net``;
commands enter it with ``nsenter``. No named namespaces, so no /run/netns and no
real root are needed.
"""

import json
import signal
import subprocess
import sys
import time
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Self, cast, override

from wrt_tests import isp, netprobe

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

UDHCPC_SCRIPT = Path(__file__).with_name("udhcpc.sh")
RUNNER_ADDRESS = "10.0.0.2"
DAEMON_SETTLE = 0.5
# The emulated internet: probe targets the tests route differently (direct or
# through the proxy), the ISP's resolver, and the socks5 exit.
INET_GATEWAY = ("203.0.113.1", "2001:db8:ffff::1")
DIRECT_TARGET = ("203.0.113.10", "2001:db8:ffff::10")
PROXIED_TARGET = ("203.0.113.20", "2001:db8:ffff::20")
PROXY_GATEWAY = ("198.51.100.1", "2001:db8:53::1")
PROXY = ("198.51.100.53", "2001:db8:53::53")
PROXY_PORT = 1080
IPERF_PORTS = (5201, 5202)


@dataclass(frozen=True, slots=True)
class Bridge:
    """A bridge in the sandbox; ``tap`` is the emulator's port on it, if any."""

    name: str
    tap: str | None = None
    address: str | None = None


@dataclass(frozen=True, slots=True)
class Port:
    """A namespace's veth to a bridge: static ``addresses``, a DHCP client, or neither."""

    bridge: str
    addresses: tuple[str, ...] = ()
    dhcp: bool = False


@dataclass(frozen=True, slots=True)
class Namespace:
    """A network namespace; its ports are eth0, eth1, ... in order.

    ``sysctls`` are ``key=value`` settings of the namespace, ``routes`` are ``ip
    route add`` arguments. ``daemons`` are command lines started inside the
    namespace; ``{workdir}`` in an argument is replaced with a private directory
    of that namespace.
    """

    name: str
    ports: tuple[Port, ...]
    sysctls: tuple[str, ...] = ()
    routes: tuple[str, ...] = ()
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
        Bridge("br-inet"),
    ),
    namespaces=(
        Namespace("client-a", ports=(Port("br-lan", dhcp=True),)),
        Namespace("client-b", ports=(Port("br-lan", dhcp=True),)),
        Namespace(
            "isp",
            ports=(
                Port("br-wan"),
                Port(
                    "br-inet",
                    addresses=tuple(
                        f"{gateway}/{length}"
                        for gateways in (INET_GATEWAY, PROXY_GATEWAY)
                        for gateway, length in zip(gateways, (24, 64), strict=True)
                    ),
                ),
            ),
            sysctls=(
                "net.ipv4.ip_forward=1",
                "net.ipv6.conf.all.forwarding=1",
                # A session's link-local address is its own: kea binds to it as
                # soon as IPv6CP is up, before duplicate detection would end.
                "net.ipv6.conf.default.accept_dad=0",
            ),
            daemons=(
                (
                    "pppoe-server",
                    "-F",
                    "-I",
                    "eth0",
                    "-L",
                    isp.BRAS_ADDRESS,
                    "-R",
                    isp.POOL_START,
                    "-N",
                    str(isp.POOL_SIZE),
                    "-O",
                    "/etc/ppp/pppoe-server-options",
                ),
            ),
        ),
        Namespace(
            "inet",
            ports=(
                Port(
                    "br-inet",
                    addresses=tuple(
                        f"{address}/{length}"
                        for addresses in (isp.DNS, DIRECT_TARGET, PROXIED_TARGET)
                        for address, length in zip(addresses, (24, 64), strict=True)
                    ),
                ),
            ),
            routes=tuple(f"default via {gateway}" for gateway in INET_GATEWAY),
            daemons=(
                (sys.executable, "-m", "wrt_tests.netprobe", "serve", "--port", str(netprobe.PORT)),
                (
                    "dnsmasq",
                    "--keep-in-foreground",
                    "--conf-file=/dev/null",
                    # Empty user and group: keep the sandbox's identity; setgroups
                    # is not allowed in a user namespace.
                    "--user=",
                    "--group=",
                    "--log-facility=-",
                    "--log-queries",
                    "--pid-file=",
                    "--bind-interfaces",
                    *(f"--listen-address={address}" for address in isp.DNS),
                    "--no-resolv",
                    "--no-hosts",
                    # The one zone the internet serves, anything else is
                    # NXDOMAIN (host records win over address rules). Every name
                    # under any.example.net resolves, so each test query can be
                    # one no cache has seen. Not a .test zone: the router's
                    # dnsmasq keeps RFC 6761 names local and never forwards them.
                    "--address=/#/",
                    f"--address=/any.example.net/{DIRECT_TARGET[0]}",
                    "--host-record=direct.example.net,{},{}".format(*DIRECT_TARGET),
                    "--host-record=proxied.example.net,{},{}".format(*PROXIED_TARGET),
                ),
                *(("iperf3", "--server", "--port", str(port)) for port in IPERF_PORTS),
            ),
        ),
        Namespace(
            "proxy",
            ports=(
                Port(
                    "br-inet",
                    addresses=tuple(
                        f"{address}/{length}"
                        for address, length in zip(PROXY, (24, 64), strict=True)
                    ),
                ),
            ),
            routes=tuple(f"default via {gateway}" for gateway in PROXY_GATEWAY),
            daemons=(("microsocks", "-i", "::", "-p", str(PROXY_PORT)),),
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
        """Run a command inside the namespace and return its output; errors show stderr."""
        try:
            result = subprocess.run(
                self.argv(*command), check=True, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.CalledProcessError as error:
            error.add_note(f"{self.name}: {error.stderr.strip()}")
            raise
        return result.stdout

    def spawn(self, *command: str, stdout: int | None = None) -> subprocess.Popen[bytes]:
        """Start a long-running command inside the namespace (``stdout``: e.g. PIPE)."""
        return subprocess.Popen(self.argv(*command), stdin=subprocess.DEVNULL, stdout=stdout)

    def probe(self, *args: str, timeout: float = 30) -> netprobe.Seen:
        """Run a netprobe client inside the namespace and return what it printed."""
        output = self.run(sys.executable, "-m", "wrt_tests.netprobe", *args, timeout=timeout)
        return cast("netprobe.Seen", json.loads(output))

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
        self._dhcp: dict[str, subprocess.Popen[bytes]] = {}

    def __getitem__(self, name: str) -> Netns:
        """Return a namespace of the topology by name."""
        return self._namespaces[name]

    @override
    def __enter__(self) -> Self:
        """Create bridges, taps and namespaces, then start DHCP clients and daemons."""
        self._isolate()
        ip("link", "set", "lo", "up")
        for bridge in self.topology.bridges:
            ip("link", "add", "name", bridge.name, "type", "bridge")
            if bridge.tap:
                ip("tuntap", "add", "dev", bridge.tap, "mode", "tap")
                ip("link", "set", bridge.tap, "master", bridge.name, "up")
            ip("link", "set", bridge.name, "up")
            if bridge.address:
                ip("addr", "add", bridge.address, "dev", bridge.name)
        for namespace in self.topology.namespaces:
            self.add(namespace)
        return self

    def _isolate(self) -> None:
        """Give the sandbox its own accounts and the ISP's /etc/ppp.

        The sandbox has one uid, 0, which is the invoking user outside. Its own
        passwd and group make every account that uid, with a private home:
        daemons that switch to an account (rp-pppoe drops to nobody) or read a
        dotfile (pppd reads ~/.ppprc) stay inside the sandbox. The host's name
        service cache would answer with the host's accounts, so its socket is
        hidden.
        """
        etc = self.workdir / "etc"
        home = self.workdir / "home"
        home.mkdir(parents=True)
        etc.mkdir()
        (etc / "passwd").write_text(
            f"root:x:0:0::{home}:/bin/sh\nnobody:x:0:0::/var/empty:/bin/false\n"
        )
        (etc / "group").write_text("root:x:0:\nnogroup:x:0:\n")
        isp.configure(etc / "ppp", self.workdir / "isp")
        for name in ("passwd", "group", "ppp"):
            subprocess.run(["mount", "--bind", etc / name, f"/etc/{name}"], check=True)
        if Path("/var/run/nscd/socket").exists():
            subprocess.run(["mount", "-t", "tmpfs", "tmpfs", "/var/run/nscd"], check=True)

    def add(self, namespace: Namespace) -> Netns:
        """Add a namespace to the running sandbox; it lives as long as the sandbox."""
        netns = self._stack.enter_context(Netns(namespace.name))
        self._namespaces[namespace.name] = netns
        netns.run("ip", "link", "set", "lo", "up")
        if namespace.sysctls:
            netns.run("sysctl", "-qw", *namespace.sysctls)
        for index, port in enumerate(namespace.ports):
            self._connect(netns, f"eth{index}", port)
        for route in namespace.routes:
            netns.run("ip", "route", "add", *route.split())
        workdir = self.workdir / namespace.name
        workdir.mkdir(parents=True, exist_ok=True)
        for daemon in namespace.daemons:
            self._daemon(netns, tuple(arg.format(workdir=workdir) for arg in daemon))
        return netns

    def _connect(self, netns: Netns, device: str, port: Port) -> None:
        outside = f"v{device[-1]}-{netns.name}"
        ip("link", "add", outside, "type", "veth", "peer", "name", device, "netns", str(netns.pid))
        ip("link", "set", outside, "master", port.bridge, "up")
        netns.run("ip", "link", "set", device, "up")
        for address in port.addresses:
            # Static IPv6 addresses skip duplicate address detection: nothing else
            # in the sandbox claims them, and the tests need them at once.
            netns.run(
                "ip", "addr", "add", address, "dev", device, *(("nodad",) if ":" in address else ())
            )
        if port.dhcp:
            self._dhcp[netns.name] = self._daemon(
                netns,
                (
                    *("udhcpc", "-f", "-i", device, "-s", str(UDHCPC_SCRIPT), "-A", "3"),
                    *("-x", f"hostname:{netns.name}"),
                ),
            )

    def renew(self, name: str) -> None:
        """Have a namespace's DHCP client renew its lease now (udhcpc: SIGUSR1)."""
        self._dhcp[name].send_signal(signal.SIGUSR1)

    def _daemon(self, netns: Netns, command: Sequence[str]) -> subprocess.Popen[bytes]:
        process = netns.spawn(*command)
        self._stack.callback(process.wait)
        self._stack.callback(process.terminate)
        try:
            code = process.wait(timeout=DAEMON_SETTLE)
        except subprocess.TimeoutExpired:
            return process
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
