"""services/containers: podman on the data disk, behind fw4, einat and dae like the LAN.

The app Pod (wrt_tests.app) runs from the test image in the emulated internet's
registry: uhttpd serving a page of the data disk, at a fixed address. Probes
from inside it use busybox's nc against the probe servers.
"""

import json
import subprocess
import time
from typing import TYPE_CHECKING, cast

import pytest

from wrt_tests import app, spec
from wrt_tests.datapath import DAE, hooks
from wrt_tests.net import DIRECT_TARGET, PROXIED_TARGET, PROXY
from wrt_tests.netprobe import HTTP_PORT, PORT
from wrt_tests.poll import until
from wrt_tests.storage import MOUNT

if TYPE_CHECKING:
    from wrt_tests.datapath import Online
    from wrt_tests.net import Netns
    from wrt_tests.netprobe import Seen
    from wrt_tests.storage import Disk

CAPABILITY = "services/containers"
STORAGE = f"{MOUNT}/containers/storage"
EINAT_PORTS = range(20000, 30000)
EXPOSED_PORT = 8080
FIREWALL_TIMEOUT = 30
# Nothing of an app may be in the image (the app containers' spec).
NATIVE_APPS = ("qbittorrent", "libtorrent", "qt6", "qt5", "qtbase")


@pytest.fixture(scope="module")
def pod(app_pod: Online, dae: Online) -> Online:
    """Return the router with the app Pod running and dae on (it splits the Pod's traffic)."""
    del dae  # running for the module
    return app_pod


@pytest.fixture(scope="module")
def registry(trusted_ca: Online, data_disk: Disk, app_image: str) -> tuple[Online, str]:
    """Return the router trusting the registry, with the data disk and no Pod declared yet."""
    del data_disk  # podman's storage
    return trusted_ca, app_image


def _from_container(pod: Online, host: str, port: int = PORT) -> Seen:
    """Ask a probe server what it sees of a connection from the app container."""
    output = pod.router.run(f"podman exec {app.CONTAINER} nc {host} {port} </dev/null")
    return cast("Seen", json.loads(output))


def _fetch(client: Netns, url: str) -> str | None:
    """Return the body at ``url``, or None when the request fails."""
    try:
        return client.run("curl", "--silent", "--fail", "--max-time", "5", url)
    except subprocess.CalledProcessError:
        return None


# The first test: the module's first pull, before the Pod's.
@spec(CAPABILITY, "Container storage on the data disk", "Pull an image")
def test_pull_goes_to_the_data_disk(registry: tuple[Online, str]) -> None:
    online, image = registry
    router = online.router
    mark = f"/tmp/pull-{time.time_ns()}"  # noqa: S108 (a path on the router)
    router.run(f"touch {mark} && podman pull --quiet {image}", timeout=300)
    assert router.run("podman info --format '{{.Store.GraphRoot}}'") == STORAGE
    layer = router.run(
        f"podman image inspect --format '{{{{.GraphDriver.Data.UpperDir}}}}' {image}"
    )
    assert layer.startswith(f"{STORAGE}/")
    # The SD card's overlay took no part of it: what little came there since came
    # from elsewhere (ksmbd starting on the same mount writes a few bytes).
    image = int(router.run(f"podman image inspect --format '{{{{.Size}}}}' {image}"))
    written = router.run(f"find /overlay/upper -newer {mark} -type f -exec cat {{}} + | wc -c")
    assert int(written) < image // 100


@spec(CAPABILITY, "Single firewall and single NAT", "Check the ruleset")
def test_ruleset_is_fw4_only(pod: Online, lan_host: Netns) -> None:
    del lan_host  # serving on client-a
    router = pod.router
    assert router.run("nft list tables").splitlines() == ["table inet fw4"]
    ruleset = router.run("nft list ruleset")
    assert "netavark" not in ruleset
    assert "chain forward_podman" in ruleset
    # The zone: the LAN reaches containers, containers never reach the LAN.
    assert _fetch(pod.client("client-b"), f"http://{app.ADDRESS}/") == f"{app.POD}\n"
    lan = pod.addresses("client-a")[0]
    assert pod.client("client-b").probe("tcp", lan)["address"]  # the LAN host answers
    refused = router.returncode(f"podman exec {app.CONTAINER} nc {lan} {PORT} </dev/null")
    assert refused != 0


@spec(CAPABILITY, "Single firewall and single NAT", "Container reaches the internet")
def test_container_reaches_the_internet(pod: Online) -> None:
    seen = _from_container(pod, DIRECT_TARGET[0])
    assert seen["address"] == pod.wan_address
    # einat's port, not the container's own (masquerade would keep that one).
    assert seen["port"] in EINAT_PORTS


@spec(CAPABILITY, "Single firewall and single NAT", "Expose a container port")
def test_exposed_port(pod: Online) -> None:
    router = pod.router
    router.run(
        "uci -q batch <<'EOF' && /etc/init.d/firewall reload\n"
        "set firewall.web=redirect\n"
        "set firewall.web.name='web'\n"
        "set firewall.web.src='wan'\n"
        f"set firewall.web.src_dport='{EXPOSED_PORT}'\n"
        "set firewall.web.dest='podman'\n"
        f"set firewall.web.dest_ip='{app.ADDRESS}'\n"
        f"set firewall.web.dest_port='{HTTP_PORT}'\n"
        "set firewall.web.proto='tcp'\n"
        "commit firewall\n"
        "EOF"
    )
    try:
        page = until(
            lambda: _fetch(pod.network["inet"], f"http://{pod.wan_address}:{EXPOSED_PORT}/"),
            timeout=FIREWALL_TIMEOUT,
            what="the forwarded port",
        )
        assert page == f"{app.POD}\n"
    finally:
        router.run("uci delete firewall.web && uci commit firewall && /etc/init.d/firewall reload")


@spec(
    CAPABILITY, "Container traffic uses the transparent proxy", "Container reaches a proxied target"
)
def test_container_reaches_a_proxied_target(pod: Online) -> None:
    assert hooks(pod.router, "podman0") == DAE
    assert _from_container(pod, PROXIED_TARGET[0])["address"] == PROXY[0]
    assert _from_container(pod, DIRECT_TARGET[0])["address"] == pod.wan_address


@spec(CAPABILITY, "Declarative definition and autostart on boot", "Declaration unchanged")
def test_unchanged_declaration_is_not_rebuilt(pod: Online) -> None:
    router = pod.router
    before = app.wait_running(router)
    # What a mount of the data disk triggers; it stops the Pods first.
    router.run("/etc/init.d/wrt-containers restart")
    assert app.running(router) is None
    assert app.wait_running(router) == before


@spec(CAPABILITY, "Declarative definition and autostart on boot", "Start on boot")
def test_pod_starts_on_boot(pod: Online) -> None:
    before = app.wait_running(pod.router)
    pod.reboot()
    after = app.wait_running(pod.router)
    assert after == before  # the same container, started again
    assert _fetch(pod.client(), f"http://{app.ADDRESS}/") == f"{app.POD}\n"


@spec(CAPABILITY, "App containers stay out of the firmware", "Check the image")
def test_no_native_apps(pod: Online) -> None:
    listed = pod.router.run("apk list --installed").splitlines()
    installed = [line.split()[0] for line in listed]
    assert "podman" in {name.rsplit("-", 2)[0] for name in installed}
    assert not [name for name in installed if name.startswith(NATIVE_APPS)]
