"""network/qos: qosify shapes WAN egress with cake, fairly across hosts, by class.

The fairness test sets the upload rate to 20 Mbit/s, and the ingress shaping
test the download rate to 10 Mbit/s, which the emulator can saturate, so their
results do not depend on the host's speed (design D11).
"""

import json
import re
import subprocess
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.model.poll import until
from wrt_tests.sandbox.net import DIRECT_TARGET, IPERF_PORTS
from wrt_tests.services import qos
from wrt_tests.services.datapath import WAN, hooks

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.device.router import Router
    from wrt_tests.services.datapath import Online

CAPABILITY = "network/qos"
DEFAULT_RATE = "100Mbit"
FAIR_RATE = "20mbit"
FAIR_SECONDS = 60
FAIRNESS = 0.2
VOICE_PORT = 3478  # STUN, a voice rule of /etc/qosify/50-wrt.conf
RECOVERY = 60
# Ingress shaping: the interface's ifb, the rate, and how long the download runs.
IFB = "ifb-pppoe-wan"
DOWN_RATE = 10_000_000
DOWN_SECONDS = 10
# How far above the rate a shaped download may measure.
DOWN_MARGIN = 1.2


def _cake(router: Router, device: str = "pppoe-wan") -> str:
    return router.run(f"tc -s qdisc show dev {device} root")


def _sent_bytes(router: Router, device: str) -> int:
    """Return the bytes the root qdisc of ``device`` has sent."""
    (sent,) = re.findall(r"Sent (\d+) bytes", _cake(router, device))
    return int(sent)


def _ifbs(router: Router) -> list[str]:
    return router.run("ls /sys/class/net | grep '^ifb' || true").split()


def _set_wan(router: Router, options: dict[str, str]) -> None:
    """Set (or, given "", delete) options of qosify's wan interface, and reload qosify."""
    commands = [
        f"uci set qosify.wan.{name}={value}" if value else f"uci -q delete qosify.wan.{name}"
        for name, value in options.items()
    ]
    router.run(" ; ".join([*commands, "uci commit qosify", "/etc/init.d/qosify reload"]))


@contextmanager
def _ingress_shaped(router: Router, rate: int) -> Iterator[None]:
    """Shape pppoe-wan's ingress with cake at ``rate`` bit/s for the block."""
    options = ("ingress", "bandwidth_down")
    previous = {
        name: router.run(f"uci -q get qosify.wan.{name} || true").strip() for name in options
    }
    _set_wan(router, {"ingress": "1", "bandwidth_down": f"{rate // 1_000_000}mbit"})
    try:
        shown = f"bandwidth {rate // 1_000_000}Mbit"
        until(
            lambda: shown in (router.poll(f"tc qdisc show dev {IFB} root") or ""),
            timeout=RECOVERY,
            what=f"cake on {IFB}",
        )
        yield
    finally:
        _set_wan(router, previous)


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
    assert _ifbs(router) == []
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
    before = qos.voice_packets(online.router)
    for _ in range(20):
        online.client().probe("send", DIRECT_TARGET[0], "--port", str(VOICE_PORT))
    assert qos.voice_packets(online.router) >= before + 20


@spec(CAPABILITY, "DSCP classification", "Classify by DNS name")
def test_dns_rule_reaches_the_voice_tin(internet_zone: Online) -> None:
    router = internet_zone.router
    with qos.rules(router, f"dns:{qos.VOICE_NAMES}\tvoice"):
        before = qos.voice_packets(router)
        address = qos.send_by_name(internet_zone, 20)
        assert address == DIRECT_TARGET[0]
        # qosify learnt the address from the reply on pppoe-wan, which has no
        # link-layer header.
        assert address in qos.learnt(router).get("ipv4", [])
        assert qos.voice_packets(router) >= before + 20


@spec(CAPABILITY, "Ingress shaping when configured", "Enable ingress shaping")
def test_ingress_shaping_takes_the_download(online: Online) -> None:
    router = online.router
    with _ingress_shaped(router, DOWN_RATE):
        before = _sent_bytes(router, IFB)
        download = online.client().run(
            *("iperf3", "--client", DIRECT_TARGET[0], "--port", str(IPERF_PORTS[0])),
            *("--reverse", "--time", str(DOWN_SECONDS), "--json"),
            timeout=DOWN_SECONDS * 3,
        )
        received = json.loads(download)["end"]["sum_received"]
        # Every byte of the download went through cake on the ifb, headers on top.
        assert _sent_bytes(router, IFB) - before >= received["bytes"]
        assert received["bits_per_second"] <= DOWN_RATE * DOWN_MARGIN
    assert _ifbs(router) == []


@spec(CAPABILITY, "Recovery after redial", "PPPoE redial")
def test_shaping_returns_after_a_redial(online: Online) -> None:
    online.redial()
    # Online waits for qosify's classifier on the new pppoe-wan, and times it.
    assert online.recovery <= RECOVERY
    assert hooks(online.router, "pppoe-wan") == WAN
    assert "qdisc cake" in _cake(online.router)
