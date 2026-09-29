"""network/qos: qosify shapes WAN egress with cake, fairly across hosts, by class.

The fairness test sets the upload rate to 20 Mbit/s, which the emulator can
saturate, so its result does not depend on the host's speed (design D11).
"""

import json
import re
import subprocess
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.datapath import QOSIFY, hooks
from wrt_tests.net import DIRECT_TARGET, IPERF_PORTS
from wrt_tests.poll import until

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.datapath import Online
    from wrt_tests.router import Router

CAPABILITY = "network/qos"
DEFAULT_RATE = "100Mbit"
FAIR_RATE = "20mbit"
FAIR_SECONDS = 60
FAIRNESS = 0.2
VOICE_PORT = 3478  # STUN, a voice rule of /etc/qosify/50-wrt.conf
RECOVERY = 60


def _cake(router: Router) -> str:
    return router.run("tc -s qdisc show dev pppoe-wan root")


def _voice_packets(router: Router) -> int:
    """Return the packets cake has sent from its Voice tin on pppoe-wan.

    diffserv4's tins are Bulk, Best Effort, Video and Voice, in this order, so
    Voice is the last column of the statistics.
    """
    lines = _cake(router).splitlines()
    assert any(line.split()[-1:] == ["Voice"] for line in lines), lines
    (packets,) = [line.split() for line in lines if line.split()[:1] == ["pkts"]]
    return int(packets[-1])


def _shape(router: Router, rate: str) -> None:
    router.run(f"uci set qosify.wan.bandwidth_up={rate} && uci commit qosify")
    router.run("/etc/init.d/qosify reload")
    shown = rate.replace("mbit", "Mbit")
    until(lambda: f"bandwidth {shown}" in _cake(router), timeout=RECOVERY, what=f"cake at {rate}")


@pytest.fixture
def fair_rate(online: Online) -> Iterator[Online]:
    """Shape at FAIR_RATE for the test."""
    _shape(online.router, FAIR_RATE)
    yield online
    _shape(online.router, DEFAULT_RATE.lower())


@spec(CAPABILITY, "Shape upload only", "Inspect queueing disciplines")
def test_cake_shapes_upload_only(online: Online) -> None:
    router = online.router
    assert re.search(rf"qdisc cake \S+ root .*bandwidth {DEFAULT_RATE}", _cake(router))
    assert "overhead 46" in _cake(router)
    ifbs = router.run("ls /sys/class/net | grep '^ifb' || true").split()
    assert ifbs == ["ifb-dns"]
    assert "cake" not in router.run("tc qdisc show dev ifb-dns")
    assert router.run("tc qdisc show dev pppoe-wan ingress").count("cake") == 0


@spec(CAPABILITY, "Fair sharing across internal hosts", "Two hosts upload at full speed")
def test_two_hosts_share_the_upload(fair_rate: Online) -> None:
    uploads = [
        fair_rate.client(name).spawn(
            *("iperf3", "--client", DIRECT_TARGET[0], "--port", str(port)),
            *("--time", str(FAIR_SECONDS), "--json"),
            stdout=subprocess.PIPE,
        )
        for name, port in zip(("client-a", "client-b"), IPERF_PORTS, strict=True)
    ]
    rates = [
        json.loads(upload.communicate(timeout=FAIR_SECONDS * 3)[0])["end"]["sum_sent"][
            "bits_per_second"
        ]
        for upload in uploads
    ]
    assert abs(rates[0] - rates[1]) <= FAIRNESS * max(rates), rates


@spec(CAPABILITY, "DSCP classification", "Classify into the voice tin")
def test_voice_rule_reaches_the_voice_tin(online: Online) -> None:
    before = _voice_packets(online.router)
    for _ in range(20):
        online.client().probe("send", DIRECT_TARGET[0], "--port", str(VOICE_PORT))
    assert _voice_packets(online.router) >= before + 20


@spec(CAPABILITY, "Recovery after redial", "PPPoE redial")
def test_shaping_returns_after_a_redial(online: Online) -> None:
    online.redial()
    # Online waits for qosify's classifier on the new pppoe-wan, and times it.
    assert online.recovery <= RECOVERY
    assert hooks(online.router, "pppoe-wan").items() >= QOSIFY.items()
    assert "qdisc cake" in _cake(online.router)
