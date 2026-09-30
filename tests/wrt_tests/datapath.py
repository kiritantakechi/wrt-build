"""The router online behind the emulated ISP, and what its datapath looks like.

``Online`` is the router with its dial-up credentials pushed: its PPP session at
the ISP, its WAN address, the LAN clients with their addresses, and a redial.
The rest reads the datapath's state on the router: which programs sit on which
tc hook of a device (``hooks``), and the configuration dae runs with in the tests.
"""

import ipaddress
import json
import re
import shlex
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self, cast

from wrt_tests.internet import RELEASES
from wrt_tests.isp import DELEGATED_PREFIX, LOGIN
from wrt_tests.net import PROXIED_TARGET, PROXY, PROXY_PORT
from wrt_tests.poll import until

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from wrt_tests.isp import Isp, Session
    from wrt_tests.net import Netns, Network
    from wrt_tests.router import Router

ONLINE_TIMEOUT = 180
DAE_TIMEOUT = 120
# The programs of each component, as bpftool names them.
EINAT = {"tcx/ingress": ["ingress_rev_snat"], "tcx/egress": ["egress_snat"]}
QOSIFY = {"clsact/ingress": ["qosify_ingress_ip"], "clsact/egress": ["qosify_egress_ip"]}
# dae on a bridge (br-lan, podman0) runs the L2 variants of its LAN programs.
DAE = {"tcx/ingress": ["tproxy_lan_ingress_l2"], "tcx/egress": ["tproxy_lan_egress_l2"]}
# The fw4 rules einat's instance brings (feed/net/einat/files/init): its nat rule
# (no masquerade) and its rule (accept what it translated back). They come with a
# firewall reload, after its programs are attached; fw4 names them after the
# instance, "ubus:einat[instance1] nat 0".
EINAT_RULE = re.compile(r"ubus:einat\[\w+\] (nat|rule) \d+")
LAN_CLIENTS = ("client-a", "client-b")
# What a wait for the datapath on pppoe-wan reports when it times out: which device
# qosify took for each of its interfaces and whether it set it up, the device as
# it is now, what tc holds on it, and the end of the log. tailscaled logs every
# route change, and the emulated ISP advertises its prefixes every few seconds.
WAN_STATE = (
    "{ ubus call qosify status; ip -o link show dev pppoe-wan; tc qdisc show dev pppoe-wan;"
    " tc filter show dev pppoe-wan ingress; tc filter show dev pppoe-wan egress;"
    " logread | grep -v tailscaled | tail -n 40; } 2>&1"
)
# How long a LAN client that is not set up is left before it asks for its lease
# again: every request starts its DHCP client over, and a router that is slow to
# answer would never see one through if asked more often.
RENEW_INTERVAL = 30.0

# dae in the tests: the socks5 exit on the emulated internet is the only node;
# PROXIED_TARGET goes through it, and so does the Releases stand-in, as GitHub
# does for an administrator whose ISP reaches it badly (r4s-release-pipeline
# D4); everything else goes direct. DNS goes to the resolver the ISP hands out.
# Debug logging shows every DNS query. dae would first wait (up to 5 minutes)
# until public test URLs answer, which the emulated internet does not serve.
PROXIED = (*PROXIED_TARGET, RELEASES[1])


def dae_config(proxied: Sequence[str] = PROXIED) -> str:
    """Return dae's test configuration, with ``proxied`` (addresses) through the proxy."""
    addresses = ", ".join(f"'{address}'" if ":" in address else address for address in proxied)
    rule = f"dip({addresses}) -> proxy\n    " if proxied else ""
    return f"""\
global {{
    log_level: debug
    disable_waiting_network: true
    check_interval: 600s
}}

node {{
    exit: 'socks5://{PROXY[0]}:{PROXY_PORT}'
}}

group {{
    proxy {{
        policy: fixed(0)
    }}
}}

dns {{
    upstream {{
        isp: 'udp://203.0.113.53:53'
    }}
    routing {{
        request {{
            fallback: isp
        }}
    }}
}}

routing {{
    {rule}fallback: direct
}}
"""


DAE_CONFIG = dae_config()


def hooks(router: Router, device: str) -> dict[str, list[str]]:
    """Return the BPF programs on ``device`` by hook ("tcx/ingress", ...), in run order."""
    found: dict[str, list[str]] = defaultdict(list)
    for line in router.run(f"bpftool net show dev {device}").splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0].startswith(f"{device}("):  # noqa: PLR2004
            found[fields[1]].append(fields[2])
    return dict(found)


def interface(router: Router, name: str) -> dict[str, Any]:
    """Return netifd's status of a logical interface."""
    return cast("dict[str, Any]", json.loads(router.run(f"ifstatus {name}")))


def lan_addresses(client: Netns) -> tuple[str, str] | None:
    """Return a LAN client's IPv4 address and global IPv6 address, once it can use both.

    An IPv6 address is usable once duplicate address detection is done with it
    (no longer tentative); before, no connection can take it as its source.
    """
    lines = client.run("ip", "-o", "addr", "show", "dev", "eth0").splitlines()
    addresses = [line.split()[3].split("/")[0] for line in lines if " tentative " not in line]
    ipv4 = [a for a in addresses if ":" not in a]
    ipv6 = [a for a in addresses if ":" in a and ipaddress.IPv6Address(a) in DELEGATED_PREFIX]
    return (ipv4[0], ipv6[0]) if ipv4 and ipv6 else None


def dhcp_leases(router: Router) -> dict[str, int]:
    """Return the router's DHCP leases: each client's hostname and when its lease ends."""
    leases = {}
    for line in router.run("cat /tmp/dhcp.leases").splitlines():
        match line.split():
            case [expiry, _, _, hostname, *_]:
                leases[hostname] = int(expiry)
            case _:
                pass
    return leases


def _session(router: Router, isp: Isp, other_than: Session | None) -> Session | None:
    status = interface(router, "wan")
    addresses = status.get("ipv4-address") or []
    if not status.get("up") or not addresses:
        return None
    peer = str(addresses[0]["address"])
    if other_than is not None and peer == other_than.peer:
        return None
    return isp.session(peer)


@dataclass
class Online:
    """The router dialed in at the ISP, with the LAN clients configured."""

    router: Router
    isp: Isp
    network: Network
    session: Session
    recovery: float = 0.0
    # The leases the LAN clients held when the router came back, which they
    # renew, and when each client last asked for its lease.
    stale_leases: dict[str, int] = field(default_factory=dict, repr=False)
    asked: dict[str, float] = field(default_factory=dict, repr=False)

    @classmethod
    def dial(cls, router: Router, isp: Isp, network: Network) -> Self:
        """Push the credentials and wait until the router is online.

        The router has just jumped back to its snapshot, so the LAN clients
        announce themselves again, as they would to a router that has come back:
        a lease renewal (with their hostname) and a router solicitation. The
        snapshot still holds their leases from the boot; they count once renewed.
        """
        user, password = map(shlex.quote, LOGIN)
        router.run(
            f"uci set network.wan.username={user} && uci set network.wan.password={password}"
            " && uci commit network && ifup wan"
        )
        stale = dhcp_leases(router)
        asked = time.monotonic()
        for name in LAN_CLIENTS:
            network.renew(name)
        online = cls(
            router,
            isp,
            network,
            _wait_session(router, isp, None),
            stale_leases=stale,
            asked=dict.fromkeys(LAN_CLIENTS, asked),
        )
        online.wait_datapath()
        return online

    @property
    def wan_address(self) -> str:
        """The address the ISP gave the router."""
        return self.session.peer

    def client(self, name: str = "client-a") -> Netns:
        """Return a LAN client's namespace."""
        return self.network[name]

    def addresses(self, name: str = "client-a") -> tuple[str, str]:
        """Return a LAN client's IPv4 and global IPv6 addresses."""
        found = lan_addresses(self.client(name))
        assert found is not None, f"{name} has no addresses"  # noqa: S101
        return found

    def reboot(self, *, while_off: Callable[[], object] | None = None) -> None:
        """Reboot the router and wait until it is online again, with the LAN clients.

        ``while_off`` changes hardware while the router is off (Router.reboot).
        """
        self.router.reboot(while_off=while_off)
        self.reconnected()

    def redial(self) -> Session:
        """End the session from the ISP side, wait until online again; return the old one."""
        self.isp.hang_up(self.session)
        return self.reconnected()

    def reconnected(self) -> Session:
        """Wait for a new session (after the old one ended) and the datapath; return the old.

        ``recovery`` is then how long einat and qosify took to attach to the new
        pppoe-wan, counted from the session coming up.
        """
        previous = self.session
        self.session = _wait_session(self.router, self.isp, previous)
        self.wait_datapath()
        return previous

    def wait_datapath(self) -> None:
        """Wait for einat and qosify on pppoe-wan, the delegated prefix and the LAN clients."""
        start = time.monotonic()
        try:
            until(
                lambda: hooks(self.router, "pppoe-wan") == {**EINAT, **QOSIFY},
                timeout=ONLINE_TIMEOUT,
                what="einat and qosify on pppoe-wan",
            )
        except TimeoutError as error:
            error.add_note(f"pppoe-wan holds {hooks(self.router, 'pppoe-wan')}")
            error.add_note(self.router.run(WAN_STATE))
            raise
        self.recovery = time.monotonic() - start
        until(
            lambda: set(EINAT_RULE.findall(self.router.run("nft list ruleset"))) == {"nat", "rule"},
            timeout=ONLINE_TIMEOUT,
            what="einat's firewall rules",
        )
        until(
            lambda: interface(self.router, "wan6").get("ipv6-prefix"),
            timeout=ONLINE_TIMEOUT,
            what="delegated prefix",
        )
        for name in LAN_CLIENTS:
            until(
                lambda n=name: self._lan_ready(n),
                timeout=ONLINE_TIMEOUT,
                what=f"{name} addresses and routes",
                every=3,
            )

    def _lan_ready(self, name: str) -> bool:
        """Return whether a LAN client is set up and the router knows it.

        That is: its addresses, an IPv6 default route, and a lease at the router,
        with its hostname, newer than the one it had to renew. A client that is
        not there yet asks again, as a host does when it (re)attaches: a router
        solicitation, and a lease renewal once its last request had time.
        """
        client = self.client(name)
        lease = dhcp_leases(self.router).get(name)
        if (
            lan_addresses(client)
            and client.run("ip", "-6", "route", "show", "default")
            and lease is not None
            and lease > self.stale_leases.get(name, 0)
        ):
            return True
        client.probe("solicit-router", "eth0")
        if time.monotonic() - self.asked.get(name, 0.0) > RENEW_INTERVAL:
            self.network.renew(name)
            self.asked[name] = time.monotonic()
        return False


def _wait_session(router: Router, isp: Isp, other_than: Session | None) -> Session:
    return until(
        lambda: _session(router, isp, other_than), timeout=ONLINE_TIMEOUT, what="PPP session"
    )


def dae_start(router: Router, config: str = DAE_CONFIG) -> None:
    """Install ``config`` as the user configuration, enable dae and wait for it on br-lan."""
    router.run(
        f"umask 077 && printf %s {shlex.quote(config)} >/etc/dae/config.dae"
        " && uci set dae.config.enabled=1 && uci commit dae && /etc/init.d/dae restart"
    )
    until(
        lambda: hooks(router, "br-lan") == DAE,
        timeout=DAE_TIMEOUT,
        what="dae on br-lan",
    )
