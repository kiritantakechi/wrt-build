"""qosify on the router: rules of a test's own, what it learns by name, and cake's tins.

A test adds its rules in a file beside the image's (``RULES``), and takes them
away again with the addresses qosify learnt from them by name: those outlive
the rule, for as long as they are in use.
"""

import json
import shlex
import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Generator

    from wrt_tests.device.router import Router
    from wrt_tests.services.datapath import Online

# Read with the image's own rules: the init script loads /etc/qosify/*.conf.
RULES = "/etc/qosify/90-test.conf"
# The kinds of addresses qosify learns from DNS replies: as its dump names them,
# and as its remove method takes them.
LEARNT = {"ipv4_addr": "ipv4", "ipv6_addr": "ipv6"}
# Names a test's dns: rule can send to a class. Every name under any.example.net
# resolves on the emulated internet, so each can be one no cache has seen.
VOICE_NAMES = "*.voice.any.example.net"
# A port no rule of the image's names: a flow there is voice by name alone.
NAMED_PORT = 4000


def voice_packets(router: Router, device: str = "pppoe-wan") -> int:
    """Return the packets cake has sent from its Voice tin on ``device``.

    diffserv4's tins are Bulk, Best Effort, Video and Voice, in this order, so
    Voice is the last column of the statistics.
    """
    lines = router.run(f"tc -s qdisc show dev {device} root").splitlines()
    if not any(line.split()[-1:] == ["Voice"] for line in lines):
        message = f"cake on {device} has no Voice tin: {lines}"
        raise ValueError(message)
    (packets,) = [line.split() for line in lines if line.split()[:1] == ["pkts"]]
    return int(packets[-1])


def learnt(router: Router) -> dict[str, list[str]]:
    """Return the addresses qosify learnt from DNS replies, by kind ("ipv4", "ipv6")."""
    found: dict[str, list[str]] = {}
    for entry in json.loads(router.run("ubus call qosify dump"))["entries"]:
        if entry["user"] and entry["type"] in LEARNT:
            found.setdefault(LEARNT[entry["type"]], []).append(entry["addr"])
    return found


def forget_learnt(router: Router) -> None:
    """Have qosify forget the addresses it learnt from DNS replies."""
    if addresses := learnt(router):
        router.run(f"ubus call qosify remove {shlex.quote(json.dumps(addresses))}")


@contextmanager
def rules(router: Router, *lines: str) -> Generator[None]:
    """Have qosify classify by ``lines`` too, in its rule files' syntax, for the block."""
    forget_learnt(router)
    router.run(f"printf '%s\\n' {shlex.join(lines)} >{RULES} && /etc/init.d/qosify reload")
    try:
        yield
    finally:
        router.run(f"rm -f {RULES} && /etc/init.d/qosify reload")
        forget_learnt(router)


def send_by_name(online: Online, packets: int) -> str:
    """Send ``packets`` datagrams from a LAN client to NAMED_PORT of a VOICE_NAMES name.

    The client resolves a fresh name through the router; return the address it got.
    """
    client = online.client()
    name = VOICE_NAMES.replace("*", uuid.uuid4().hex[:12])
    answer = client.probe("resolve", name, "--server", online.router.address)
    answers = cast("list[str]", answer["answers"])
    if answer["rcode"] != 0 or len(answers) != 1:
        message = f"{name} resolved to {answer}"
        raise LookupError(message)
    (address,) = answers
    for _ in range(packets):
        client.probe("send", address, "--port", str(NAMED_PORT))
    return address
