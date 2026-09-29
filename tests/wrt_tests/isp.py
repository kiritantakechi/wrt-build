"""The emulated ISP between the router's WAN and the emulated internet (r4s-ebpf-datapath D11).

The ``isp`` namespace is the BRAS. rp-pppoe's pppoe-server runs in user mode (a
pty per session, so the host needs only ppp_generic and ppp_async, never
pppoe.ko) and hands each session the next address of its pool: every redial
gets a new address. pppd runs four scripts per session:

- ``ip-up`` and ``ip-down`` keep a registry for the tests, one file per session
  (named after its pppd) with its PPP interface and the address the peer got;
- ``ipv6-up`` gives the session the WAN prefix for SLAAC (radvd) and a delegated
  prefix (kea-dhcp6), and ``ipv6-down`` stops both. The prefixes stay the same
  across redials, so only the IPv4 address moves.

Everything is keyed by the session's pppd, never by its interface: a redial may
get the same interface name while the previous session is still going down.

pppd reads its options and secrets from fixed paths under /etc/ppp, and looks
up root's home for ``~/.ppprc``; the sandbox mounts what ``configure`` writes
there (``wrt_tests.net``). The scripts stay in the ISP's own directory, named by
the server options, so that a pppd dialing from a test runs none of them.
"""

import ipaddress
import json
import os
import shutil
import signal
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.net import Netns

# The account the router dials with; the image carries none (the config push
# writes the real one).
LOGIN = ("wrt", "sandbox")
BRAS_ADDRESS = "192.0.2.1"
POOL_START = "192.0.2.64"
POOL_SIZE = 64
MTU = 1492
# The resolver the ISP hands out, served on the emulated internet.
DNS = ("203.0.113.53", "2001:db8:ffff::53")
# SLAAC on every session's link, and the prefix delegated to the router.
WAN_PREFIX = "2001:db8:0:1::/64"
WAN_GATEWAY = "2001:db8:0:1::1"
DELEGATED_PREFIX = ipaddress.IPv6Network("2001:db8:100::/56")
SESSION_TIMEOUT = 60


@dataclass(frozen=True, slots=True)
class Session:
    """A PPP session as the ISP sees it."""

    interface: str
    pid: int
    peer: str


class Isp:
    """The tests' handle on the ISP: its sessions, and hanging them up."""

    def __init__(self, netns: Netns, workdir: Path) -> None:
        """Wrap the ``isp`` namespace; ``workdir`` is the one ``configure`` was given."""
        self.netns = netns
        self.registry = workdir / "sessions"

    def sessions(self) -> list[Session]:
        """Return the sessions whose IPCP is up."""
        found = []
        for entry in sorted(self.registry.iterdir()):
            if entry.suffix:
                continue
            interface, peer = entry.read_text().split()
            found.append(Session(interface, int(entry.name), peer))
        return found

    def session(self, peer: str) -> Session:
        """Wait for the session that gave ``peer`` its address and return it."""
        deadline = time.monotonic() + SESSION_TIMEOUT
        while not (found := [s for s in self.sessions() if s.peer == peer]):
            if time.monotonic() > deadline:
                msg = f"the ISP has no session for {peer}: {self.sessions()}"
                raise TimeoutError(msg)
            time.sleep(0.5)
        return found[0]

    def hang_up(self, session: Session) -> None:
        """End a session from the ISP side (pppd sends LCP terminate and PADT)."""
        os.kill(session.pid, signal.SIGTERM)
        deadline = time.monotonic() + SESSION_TIMEOUT
        while (self.registry / str(session.pid)).exists():
            if time.monotonic() > deadline:
                msg = f"session {session} did not end"
                raise TimeoutError(msg)
            time.sleep(0.2)


def configure(etc: Path, workdir: Path) -> None:
    """Write the ISP's /etc/ppp to ``etc``, and its session scripts to ``workdir``."""
    etc.mkdir(parents=True)
    (workdir / "sessions").mkdir(parents=True)
    scripts = _scripts(workdir)
    for name, body in scripts.items():
        script = workdir / name
        script.write_text(f"#!/bin/sh\n{body}")
        script.chmod(0o755)
    (etc / "options").write_text("")
    secrets = etc / "pap-secrets"
    secrets.write_text(f"{LOGIN[0]} * {LOGIN[1]} *\n")
    secrets.chmod(0o600)
    (etc / "pppoe-server-options").write_text(
        "\n".join(
            (
                "# The ISP's side of every session (pppoe-server -O).",
                "require-pap",
                f"mtu {MTU}",
                f"mru {MTU}",
                f"ms-dns {DNS[0]}",
                "lcp-echo-interval 5",
                "lcp-echo-failure 3",
                "noccp",
                "novj",
                "+ipv6",
                "debug",
                f"logfile {workdir / 'pppd.log'}",
                *(f"{name}-script {workdir / name}" for name in scripts),
                "",
            )
        )
    )


def _scripts(workdir: Path) -> dict[str, str]:
    """Return the session scripts; pppd gives them a bare PATH, so tools are absolute."""
    ip, setsid, pkill, radvd, kea = map(_tool, ("ip", "setsid", "pkill", "radvd", "kea-dhcp6"))
    registry = workdir / "sessions"
    session = f"{workdir}/${{PPPD_PID}}"
    kea_config = {
        "Dhcp6": {
            # ipv6-up runs as IPv6CP comes up, possibly before the link-local
            # address is usable: keep trying to bind for a while.
            "interfaces-config": {
                "interfaces": ["${IFNAME}"],
                "service-sockets-max-retries": 20,
                "service-sockets-retry-wait-time": 500,
            },
            "lease-database": {"type": "memfile", "persist": False},
            # A fixed server DUID, kept in memory instead of /var/lib/kea.
            "server-id": {"type": "LL", "htype": 1, "identifier": "020000000001", "persist": False},
            "renew-timer": 900,
            "rebind-timer": 1800,
            "preferred-lifetime": 3600,
            "valid-lifetime": 7200,
            "option-data": [{"name": "dns-servers", "data": DNS[1]}],
            "subnet6": [
                {
                    "id": 1,
                    "subnet": WAN_PREFIX,
                    "interface": "${IFNAME}",
                    "pd-pools": [
                        {
                            "prefix": str(DELEGATED_PREFIX.network_address),
                            "prefix-len": DELEGATED_PREFIX.prefixlen,
                            "delegated-len": DELEGATED_PREFIX.prefixlen,
                        }
                    ],
                }
            ],
            "loggers": [
                {"name": "kea-dhcp6", "output-options": [{"output": "stdout"}], "severity": "INFO"}
            ],
        }
    }
    return {
        "ip-up": (
            "# Record the session: its interface and the address the peer got.\n"
            f'printf "%s %s\\n" "${{IFNAME}}" "${{IPREMOTE}}" >"{registry}/${{PPPD_PID}}.new"\n'
            f'mv "{registry}/${{PPPD_PID}}.new" "{registry}/${{PPPD_PID}}"\n'
        ),
        "ip-down": f'rm -f "{registry}/${{PPPD_PID}}"\n',
        "ipv6-up": (
            "# SLAAC on the link (radvd) and a delegated prefix (kea-dhcp6).\n"
            "set -eu\n"
            f'mkdir -p "{session}"\n'
            # pppd sets the link-local address with the peer's; kea would bind
            # to the peer's, so the session's own becomes a plain one ($4).
            f'{ip} -6 addr flush dev "${{IFNAME}}" scope link\n'
            f'{ip} -6 addr add "$4/64" dev "${{IFNAME}}" nodad\n'
            # The newest session owns the prefixes: the previous one may still be
            # going down (its peer left without a word, as after a snapshot jump).
            f'{ip} -6 addr add {WAN_GATEWAY}/64 dev "${{IFNAME}}" nodad\n'
            f'{ip} -6 route replace {WAN_PREFIX} dev "${{IFNAME}}"\n'
            f'{ip} -6 route replace {DELEGATED_PREFIX} dev "${{IFNAME}}"\n'
            f'cat >"{session}/radvd.conf" <<EOF\n'
            "interface ${IFNAME} {\n"
            "\tAdvSendAdvert on;\n"
            "\tAdvManagedFlag on;\n"
            "\tAdvOtherConfigFlag on;\n"
            "\tMinRtrAdvInterval 3;\n"
            "\tMaxRtrAdvInterval 10;\n"
            f"\tprefix {WAN_PREFIX} {{ AdvOnLink on; AdvAutonomous on; }};\n"
            f"\tRDNSS {DNS[1]} {{}};\n"
            "};\n"
            "EOF\n"
            f'cat >"{session}/kea.json" <<EOF\n{json.dumps(kea_config, indent=1)}\nEOF\n'
            f'{setsid} -f {radvd} -n -m stderr -C "{session}/radvd.conf" -p "{session}/radvd.pid" '
            f'>"{session}/radvd.log" 2>&1 </dev/null\n'
            f'KEA_PIDFILE_DIR="{session}" KEA_LOCKFILE_DIR="{session}" '
            f'{setsid} -f {kea} -c "{session}/kea.json" >"{session}/kea.log" 2>&1 </dev/null\n'
        ),
        "ipv6-down": f'{pkill} -f -- "{session}/" || true\n',
    }


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        msg = f"{name} is not on PATH (the test environment provides it)"
        raise FileNotFoundError(msg)
    return path
