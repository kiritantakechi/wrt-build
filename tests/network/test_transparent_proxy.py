"""network/transparent-proxy: honk on the LAN side, splitting by rule into direct and proxied.

honk runs with the test configuration (wrt_tests.services.datapath.PROXY_CONFIG): the
socks5 exit on the emulated internet is its only node, PROXIED_TARGET goes through
it, everything else goes direct.
"""

import json
import re
import signal
import subprocess
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast

import pytest

from wrt_tests import spec
from wrt_tests.model.poll import until
from wrt_tests.sandbox.net import DIRECT_TARGET, PROXIED_TARGET, PROXY
from wrt_tests.sandbox.netprobe import HTTP_PORT
from wrt_tests.services import app
from wrt_tests.services.datapath import (
    NATIVE_API,
    NATIVE_API_PORT,
    PROXIED,
    PROXY_CONFIG,
    PROXY_HOOKS_L2,
    PROXY_NFQUEUE_TABLE,
    PROXY_TIMEOUT,
    hooks,
    native_api,
    proxy_config,
    proxy_pid,
    proxy_start,
    wait_proxy,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.device.router import Router
    from wrt_tests.model.boards import Board
    from wrt_tests.services.datapath import Online

CAPABILITY = "network/transparent-proxy"
HEALTHCHECK = "/etc/healthcheck.d/50-honk"
BIND_TIMEOUT = 60
# The LAN connections to the router that must all be accepted: one a second for
# a minute (honk #456 refused some of them).
ROUTER_CONNECTIONS = 60
# A request of the native API that needs a credential.
NATIVE_API_REQUEST = "/api/v1/dns/cache?name=example.net"
# honk's programs on the cgroup2 root, by attach type: its sock_ops program,
# which acts in its own network namespace only, and its socket-identity capture,
# which records a socket's process and allows every operation.
CGROUP_PROGRAMS = {
    ("cgroup_sock_ops", "honk_tcp_passive"),
    ("cgroup_inet_sock_create", "tproxy_wan_cg_sock_create"),
    ("cgroup_inet4_connect", "tproxy_wan_cg_connect4"),
    ("cgroup_inet6_connect", "tproxy_wan_cg_connect6"),
    ("cgroup_udp4_sendmsg", "tproxy_wan_cg_sendmsg4"),
    ("cgroup_udp6_sendmsg", "tproxy_wan_cg_sendmsg6"),
}


@pytest.fixture
def proxy_restored(proxy: Online) -> Iterator[Online]:
    """Put honk back with the test configuration after a test that changes or stops it."""
    yield proxy
    proxy_start(proxy.router)


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


def _init(router: Router, session: str, action: str) -> None:
    """Run an action of honk's init script as daeuniverse's LuCI page does."""
    _ubus(router, session, "rc", "init", {"name": "honk", "action": action})


@spec(CAPABILITY, "Bind LAN-side interfaces only", "Check programs on each interface")
def test_honk_binds_only_the_lan(proxy: Online) -> None:
    assert hooks(proxy.router, "br-lan") == PROXY_HOOKS_L2
    wan = hooks(proxy.router, "pppoe-wan")
    honk = re.compile(r"^(lan|wan)_(ingress|egress)_l[23]$|^dae0")
    assert not any(honk.match(name) for names in wan.values() for name in names), wan


@spec(CAPABILITY, "Bind LAN-side interfaces only", "Check the cgroup programs")
def test_honk_s_cgroup_programs_leave_the_router_s_sockets_alone(proxy: Online) -> None:
    tree = proxy.router.run("bpftool cgroup tree /sys/fs/cgroup")
    attached = set(re.findall(r"^\d+\s+(\S+)\s+\S+\s+(\S+)\s*$", tree, flags=re.MULTILINE))
    assert attached == CGROUP_PROGRAMS, tree
    body = proxy.router.run(f"uclient-fetch -qO- http://{PROXIED_TARGET[0]}:{HTTP_PORT}/")
    assert json.loads(body)["address"] == proxy.wan_address


@spec(CAPABILITY, "Bind LAN-side interfaces only", "Container bridge appears after the proxy")
def test_container_bridge_is_bound_when_it_appears(proxy: Online) -> None:
    router = proxy.router
    pid = proxy_pid(router)
    router.run("ip link add podman0 type bridge && ip link set podman0 up")
    try:
        until(
            lambda: hooks(router, "podman0") == PROXY_HOOKS_L2,
            timeout=BIND_TIMEOUT,
            what="honk on podman0",
        )
    finally:
        router.run("ip link del podman0")
    # The bridge going away leaves honk running, on br-lan as before.
    assert proxy_pid(router) == pid
    assert hooks(router, "br-lan") == PROXY_HOOKS_L2


@spec(
    CAPABILITY, "Bind LAN-side interfaces only", "Container bridge appears while the proxy starts"
)
def test_container_bridge_is_bound_when_it_appears_as_honk_starts(
    proxy_restored: Online,
) -> None:
    router = proxy_restored.router
    router.run(
        "/etc/init.d/honk restart && ip link add podman0 type bridge && ip link set podman0 up"
    )
    try:
        until(
            lambda: hooks(router, "podman0") == PROXY_HOOKS_L2,
            timeout=BIND_TIMEOUT,
            what="honk on podman0",
        )
    finally:
        router.run("ip link del podman0")


@spec(CAPABILITY, "Rule-based traffic splitting", "Access a direct target")
def test_direct_target_goes_direct(proxy: Online) -> None:
    assert proxy.client().probe("tcp", DIRECT_TARGET[0])["address"] == proxy.wan_address
    assert DIRECT_TARGET[0] not in proxy.router.run("ss -Htnp | grep honk-core || true")


@spec(CAPABILITY, "Rule-based traffic splitting", "Access a proxied target")
def test_proxied_target_goes_through_the_node(proxy: Online) -> None:
    assert proxy.client().probe("tcp", PROXIED_TARGET[0])["address"] == PROXY[0]


@spec(CAPABILITY, "Cover both IPv4 and IPv6", "Access a proxied target over IPv6")
def test_proxied_target_over_ipv6(proxy: Online) -> None:
    assert proxy.client().probe("tcp", PROXIED_TARGET[1])["address"] == PROXY[1]


@spec(CAPABILITY, "Router-originated traffic goes direct", "Router accesses an external address")
def test_router_traffic_goes_direct(proxy: Online) -> None:
    body = proxy.router.run(f"uclient-fetch -qO- http://{PROXIED_TARGET[0]}:{HTTP_PORT}/")
    assert json.loads(body)["address"] == proxy.wan_address


@spec(
    CAPABILITY,
    "The router stays reachable from bound interfaces",
    "Connect to the router from the LAN",
)
def test_the_router_answers_the_lan(proxy: Online) -> None:
    client = proxy.client()
    answers = []
    for _ in range(ROUTER_CONNECTIONS):
        answers.append(
            client.run(
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-m",
                "5",
                "-w",
                "%{http_code}",
                f"http://{proxy.router.address}/",
            )
        )
        time.sleep(1)
    assert set(answers) == {"200"}, answers


@spec(CAPABILITY, "Configuration management", "Save config in LuCI")
def test_luci_save_hot_reloads(proxy_restored: Online) -> None:
    online = proxy_restored
    router = online.router
    session = _luci_session(router)
    pid = proxy_pid(router)
    # A direct flow runs through the reload: pings every 0.1 s, none may be lost,
    # from before the write until the saved configuration is in effect. nsenter
    # runs ping in its own process: the interrupt reaches ping, which then prints
    # its summary (test-fidelity D6).
    pings = subprocess.Popen(
        online.client().argv("ping", "-i", "0.1", "-W", "1", DIRECT_TARGET[0]),
        stdout=subprocess.PIPE,
        text=True,
    )
    # The edit LuCI makes, then its save: the proxied target now goes direct as well.
    config = proxy_config([address for address in PROXIED if address not in PROXIED_TARGET])
    _ubus(
        router,
        session,
        "file",
        "write",
        {"path": "/etc/honk/config.dae", "data": config, "mode": 0o600},
    )
    _init(router, session, "reload")
    try:
        until(
            lambda: (
                online.client().probe("tcp", PROXIED_TARGET[0])["address"] == online.wan_address
            ),
            timeout=PROXY_TIMEOUT,
            what="the saved configuration in effect",
        )
    finally:
        pings.send_signal(signal.SIGINT)
        output, _ = pings.communicate(timeout=60)
    assert " 0% packet loss" in output, output
    assert proxy_pid(router) == pid
    assert hooks(router, "br-lan") == PROXY_HOOKS_L2


@spec(CAPABILITY, "Configuration management", "Inspect the image")
def test_image_carries_only_a_template(proxy: Online) -> None:
    router = proxy.router
    assert "0.1.0-beta.6" in router.run("honk-core --version")
    template = router.run("cat /rom/etc/honk/config.dae")
    sections = set(re.findall(r"^(\w+)\s*\{", template, re.MULTILINE))
    assert sections <= {"global", "routing"}, sections
    assert "://" not in template
    assert "native_api" not in template
    assert "secret" not in template
    # The image ships honk disabled: no rc.d link of its own.
    assert "honk" not in router.run("ls /rom/etc/rc.d")


@spec(CAPABILITY, "Configuration management", "Turn the proxy off")
def test_turning_honk_off_stops_it(proxy_restored: Online) -> None:
    router = proxy_restored.router
    session = _luci_session(router)
    # LuCI's Stop button, then its Start at boot switch.
    _init(router, session, "stop")
    _init(router, session, "disable")
    until(lambda: not proxy_pid(router), timeout=PROXY_TIMEOUT, what="honk stopped")
    until(lambda: not hooks(router, "br-lan"), timeout=PROXY_TIMEOUT, what="honk's programs gone")
    assert router.returncode("/etc/init.d/honk enabled") != 0


@spec(CAPABILITY, "Fall back to direct when stopped", "Stop the proxy")
def test_stopping_honk_falls_back_to_direct(proxy_restored: Online) -> None:
    online = proxy_restored
    online.router.run("/etc/init.d/honk stop")
    until(
        lambda: not hooks(online.router, "br-lan"),
        timeout=PROXY_TIMEOUT,
        what="honk's programs gone",
    )
    for target in (DIRECT_TARGET[0], PROXIED_TARGET[0]):
        assert online.client().probe("tcp", target)["address"] == online.wan_address


@spec(CAPABILITY, "Register a health check", "Proxy not running")
def test_health_check_fails_without_honk(proxy_restored: Online) -> None:
    router = proxy_restored.router
    assert router.returncode(HEALTHCHECK) == 0
    # honk running, but a program missing from a bound interface.
    link = re.findall(r"link_id (\d+)", router.run("bpftool net show dev br-lan"))[0]
    router.run(f"bpftool link detach id {link}")
    assert proxy_pid(router)
    assert router.returncode(HEALTHCHECK) != 0
    router.run("/etc/init.d/honk stop")
    assert router.returncode(HEALTHCHECK) != 0


@spec(CAPABILITY, "honk's netfilter hook outlives firewall reloads", "Reload the firewall")
def test_the_nfqueue_table_outlives_a_firewall_reload(proxy: Online) -> None:
    router = proxy.router
    before = router.run(f"nft list table {PROXY_NFQUEUE_TABLE}")
    router.run("fw4 -q reload")
    assert router.run(f"nft list table {PROXY_NFQUEUE_TABLE}") == before


@spec(
    CAPABILITY, "honk's netfilter hook outlives firewall reloads", "Stop the proxy after a reload"
)
def test_the_nfqueue_table_goes_with_honk(proxy_restored: Online) -> None:
    router = proxy_restored.router
    router.run("fw4 -q reload")
    router.run("/etc/init.d/honk stop")
    until(lambda: not proxy_pid(router), timeout=PROXY_TIMEOUT, what="honk stopped")
    assert router.returncode(f"nft list table {PROXY_NFQUEUE_TABLE}") != 0


@spec(CAPABILITY, "No other listeners", "Inspect honk's sockets")
def test_honk_listens_only_for_dns_on_loopback(proxy: Online) -> None:
    listening = proxy.router.run("ss -Hlntup | grep honk-core || true")
    local = {line.split()[4] for line in listening.splitlines()}
    assert local == {"127.0.0.1:5353"}, listening


@spec(CAPABILITY, "Optional CPU pinning", "Enable CPU pinning")
def test_cpu_pinning_takes_the_big_cores(proxy_restored: Online, board: Board) -> None:
    router = proxy_restored.router
    assert router.run("uci get honk.config.cpu_pinning") == "0"
    # The big cores: the CPUs of the highest capacity the router reports, which
    # the emulator gives the board's SoC's (testing/emulation). They are fewer
    # than all, so a honk that is not pinned runs elsewhere too.
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
    running = proxy_pid(router)
    router.run("uci set honk.config.cpu_pinning=1 && uci commit honk && /etc/init.d/honk restart")
    try:
        wait_proxy(router, replacing=running)
        assert int(router.run("taskset -p $(pidof honk-core)").split()[-1], 16) == big
    finally:
        router.run("uci set honk.config.cpu_pinning=0 && uci commit honk")


@pytest.fixture
def native_api_on(proxy_restored: Online) -> Online:
    """Run honk with its native API in token mode, as config-push lets it be."""
    proxy_start(proxy_restored.router, PROXY_CONFIG + NATIVE_API)
    return proxy_restored


@spec(CAPABILITY, "Web UI through the native API in token mode", "Native API enabled with a token")
def test_the_native_api_answers_the_lan_with_its_token(native_api_on: Online) -> None:
    lan = (native_api_on.client(), native_api_on.router.address)
    status, page = native_api(*lan, "/ui/")
    assert status == HTTPStatus.OK, page
    assert page.lower().startswith("<!doctype html>"), page[:200]
    assert native_api(*lan, NATIVE_API_REQUEST)[0] == HTTPStatus.OK
    assert native_api(*lan, NATIVE_API_REQUEST, token=None)[0] == HTTPStatus.UNAUTHORIZED


# The last test: its Pod and data disk stay for the rest of the module.
@spec(CAPABILITY, "Web UI through the native API in token mode", "Native API from outside the LAN")
def test_the_native_api_answers_nothing_outside_the_lan(
    native_api_on: Online, app_pod: Online
) -> None:
    del app_pod  # a container on the container bridge
    online = native_api_on
    # The LAN gets an answer: the native API listens.
    assert native_api(online.client(), online.router.address, "/api")[0] == HTTPStatus.OK
    assert native_api(online.network["inet"], online.wan_address, "/api")[0] == 0
    container = online.router.returncode(
        f"podman exec {app.CONTAINER} nc -w 5 {app.GATEWAY} {NATIVE_API_PORT} </dev/null"
    )
    assert container != 0
