"""network/transparent-proxy: dae on the LAN side, splitting by rule into direct and proxied.

dae runs with the test configuration (wrt_tests.services.datapath.DAE_CONFIG): the socks5
exit on the emulated internet is its only node, PROXIED_TARGET goes through it,
everything else goes direct.
"""

import json
import re
import subprocess
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast

import pytest

from wrt_tests import spec
from wrt_tests.model.poll import until
from wrt_tests.sandbox.net import DIRECT_TARGET, PROXIED_TARGET, PROXY
from wrt_tests.sandbox.netprobe import HTTP_PORT
from wrt_tests.services.datapath import DAE, DAE_TIMEOUT, PROXIED, dae_config, dae_start, hooks

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.device.router import Router
    from wrt_tests.model.boards import Board
    from wrt_tests.services.datapath import Online

CAPABILITY = "network/transparent-proxy"
HEALTHCHECK = "/etc/healthcheck.d/50-dae"
BIND_TIMEOUT = 60


@pytest.fixture
def dae_restored(dae: Online) -> Iterator[Online]:
    """Put dae back with the test configuration after a test that changes or stops it."""
    yield dae
    dae_start(dae.router)


def _luci_session(router: Router) -> str:
    """Log in to rpcd over HTTP as LuCI does; return the session."""
    reply = _ubus(
        router,
        "00000000000000000000000000000000",
        "session",
        "login",
        {"username": "root", "password": ""},
    )
    return str(reply["ubus_rpc_session"])


def _ubus(
    router: Router, session: str, path: str, method: str, arguments: dict[str, object]
) -> dict[str, object]:
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "call",
        "params": [session, path, method, arguments],
    }
    status, reply = router.http("/ubus", data=json.dumps(request).encode())
    assert status == HTTPStatus.OK, reply
    result = cast("list[Any]", json.loads(reply)["result"])
    assert result[0] == 0, result
    return cast("dict[str, object]", result[1]) if len(result) > 1 else {}


@spec(CAPABILITY, "Bind LAN-side interfaces only", "Check programs on each interface")
def test_dae_binds_only_the_lan(dae: Online) -> None:
    assert hooks(dae.router, "br-lan") == DAE
    wan = hooks(dae.router, "pppoe-wan")
    assert not any(name.startswith("tproxy") for names in wan.values() for name in names)
    assert "tproxy" not in dae.router.run("bpftool cgroup tree")
    # Design risk: dae issue #848, a conntrack warning when dae sets up its netns.
    assert not re.search(r"WARNING.*conntrack", dae.router.run("dmesg"))


@spec(CAPABILITY, "Bind LAN-side interfaces only", "Container bridge appears after dae")
def test_container_bridge_is_bound_when_it_appears(dae: Online) -> None:
    router = dae.router
    router.run("ip link add podman0 type bridge && ip link set podman0 up")
    try:
        until(lambda: hooks(router, "podman0") == DAE, timeout=BIND_TIMEOUT, what="dae on podman0")
        assert "podman0" in router.run("grep lan_interface /var/run/dae/main.dae")
    finally:
        router.run("ip link del podman0")
    # Task 5.2: the bridge going away rebinds without it, and dae keeps running.
    until(
        lambda: "podman0" not in router.run("grep lan_interface /var/run/dae/main.dae"),
        timeout=BIND_TIMEOUT,
        what="podman0 released",
    )
    assert router.returncode("pidof dae >/dev/null") == 0
    until(lambda: hooks(router, "br-lan") == DAE, timeout=BIND_TIMEOUT, what="dae on br-lan")


@spec(CAPABILITY, "Rule-based traffic splitting", "Access a direct target")
def test_direct_target_goes_direct(dae: Online) -> None:
    assert dae.client().probe("tcp", DIRECT_TARGET[0])["address"] == dae.wan_address
    assert DIRECT_TARGET[0] not in dae.router.run("ss -Htnp | grep dae || true")


@spec(CAPABILITY, "Rule-based traffic splitting", "Access a proxied target")
def test_proxied_target_goes_through_the_node(dae: Online) -> None:
    assert dae.client().probe("tcp", PROXIED_TARGET[0])["address"] == PROXY[0]


@spec(CAPABILITY, "Cover both IPv4 and IPv6", "Access a proxied target over IPv6")
def test_proxied_target_over_ipv6(dae: Online) -> None:
    assert dae.client().probe("tcp", PROXIED_TARGET[1])["address"] == PROXY[1]


@spec(CAPABILITY, "Router-originated traffic goes direct", "Router accesses an external address")
def test_router_traffic_goes_direct(dae: Online) -> None:
    body = dae.router.run(f"uclient-fetch -qO- http://{PROXIED_TARGET[0]}:{HTTP_PORT}/")
    assert json.loads(body)["address"] == dae.wan_address


@spec(CAPABILITY, "Configuration management", "Save config in LuCI")
def test_luci_save_hot_reloads(dae_restored: Online) -> None:
    online = dae_restored
    router = online.router
    session = _luci_session(router)
    # A direct flow runs through the reload: pings every 0.1 s, none may be lost.
    pings = subprocess.Popen(
        online.client().argv("ping", "-c", "100", "-i", "0.1", "-W", "1", DIRECT_TARGET[0]),
        stdout=subprocess.PIPE,
        text=True,
    )
    # The edit LuCI makes: the proxied target now goes direct as well.
    config = dae_config([address for address in PROXIED if address not in PROXIED_TARGET])
    _ubus(
        router,
        session,
        "file",
        "write",
        {"path": "/etc/dae/config.dae", "data": config, "mode": 0o600},
    )
    _ubus(router, session, "file", "exec", {"command": "/etc/init.d/dae", "params": ["hot_reload"]})
    until(
        lambda: online.client().probe("tcp", PROXIED_TARGET[0])["address"] == online.wan_address,
        timeout=DAE_TIMEOUT,
        what="the saved configuration in effect",
    )
    output, _ = pings.communicate(timeout=60)
    assert " 0% packet loss" in output, output
    assert hooks(router, "br-lan") == DAE


@spec(CAPABILITY, "Configuration management", "Inspect the image")
def test_image_carries_only_a_template(dae: Online) -> None:
    assert "2.1.1" in dae.router.run("dae --version").splitlines()[0]
    template = dae.router.run("cat /rom/etc/dae/config.dae")
    sections = set(re.findall(r"^(\w+)\s*\{", template, re.MULTILINE))
    assert sections <= {"global", "routing"}, sections
    assert "://" not in template
    assert dae.router.run("cat /rom/etc/config/dae | grep enabled").split()[-1].strip("'") == "0"


@spec(CAPABILITY, "Fall back to direct when stopped", "Stop dae")
def test_stopping_dae_falls_back_to_direct(dae_restored: Online) -> None:
    online = dae_restored
    online.router.run("/etc/init.d/dae stop")
    until(
        lambda: not hooks(online.router, "br-lan"), timeout=DAE_TIMEOUT, what="dae's programs gone"
    )
    for target in (DIRECT_TARGET[0], PROXIED_TARGET[0]):
        assert online.client().probe("tcp", target)["address"] == online.wan_address


@spec(CAPABILITY, "Register a health check", "dae not running")
def test_health_check_fails_without_dae(dae_restored: Online) -> None:
    router = dae_restored.router
    assert router.returncode(HEALTHCHECK) == 0
    # Task 5.4: dae running, but a program missing from a bound interface.
    link = re.findall(r"link_id (\d+)", router.run("bpftool net show dev br-lan"))[0]
    router.run(f"bpftool link detach id {link}")
    assert router.returncode("pidof dae >/dev/null") == 0
    assert router.returncode(HEALTHCHECK) != 0
    router.run("/etc/init.d/dae stop")
    assert router.returncode(HEALTHCHECK) != 0


@spec(CAPABILITY, "Optional CPU pinning", "Enable CPU pinning")
def test_cpu_pinning_takes_the_big_cores(dae_restored: Online, board: Board) -> None:
    router = dae_restored.router
    assert router.run("uci get dae.config.cpu_pinning") == "0"
    # The big cores: the CPUs of the highest capacity the router reports, which
    # the emulator gives the board's SoC's (testing/emulation). They are fewer
    # than all, so a dae that is not pinned runs elsewhere too.
    listing = router.run("grep -H . /sys/devices/system/cpu/cpu[0-9]*/cpu_capacity")
    capacities = {
        int(cpu): int(capacity)
        for cpu, capacity in re.findall(r"/cpu(\d+)/cpu_capacity:(\d+)", listing)
    }
    highest = max(capacities.values())
    cores = sorted(cpu for cpu, capacity in capacities.items() if capacity == highest)
    assert cores == list(board.big_cores)
    assert len(cores) < len(capacities)
    big = sum(1 << cpu for cpu in cores)
    router.run("uci set dae.config.cpu_pinning=1 && uci commit dae && /etc/init.d/dae restart")
    try:
        until(lambda: hooks(router, "br-lan") == DAE, timeout=DAE_TIMEOUT, what="dae on br-lan")
        assert int(router.run("taskset -p $(pidof dae)").split()[-1], 16) == big
    finally:
        router.run("uci set dae.config.cpu_pinning=0 && uci commit dae")
