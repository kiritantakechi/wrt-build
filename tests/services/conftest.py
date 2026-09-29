"""Fixtures of the services tests (r4s-services D10): what an administrator sets up.

An SMB user, the WireGuard tunnel and the tailnet: each is written the way the
config push or an administrator would, since the image presets none of it. A
module's router returns to its snapshot afterwards, so only what lives outside
it (wg-peer, ts-peer, headscale, the LAN host's server) is put back.
"""

import shlex
import sys
from typing import TYPE_CHECKING

import pytest

from wrt_tests.net import PROXIED_TARGET
from wrt_tests.poll import until
from wrt_tests.vpn import LAN_PREFIX, Tailnet, WireGuard

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wrt_tests.datapath import Online
    from wrt_tests.net import Netns, Network
    from wrt_tests.router import Router
    from wrt_tests.storage import Disk

SMB_USER = ("smbuser", "smb-secret-1")
SMB_TIMEOUT = 60


@pytest.fixture(scope="module")
def lan_host(network: Network) -> Iterator[Netns]:
    """Run a probe server on client-a, a host of the LAN."""
    client = network["client-a"]
    server = client.spawn(sys.executable, "-m", "wrt_tests.netprobe", "serve")
    yield client
    server.terminate()
    server.wait()


@pytest.fixture(scope="module")
def smb_user(data_disk: Disk, module_router: Router) -> tuple[str, str]:
    """Add a share user: a system account without a login, and its SMB password."""
    del data_disk  # the share is on it
    user, password = SMB_USER
    module_router.run(
        f"echo '{user}:x:1000:1000::/var:/bin/false' >>/etc/passwd"
        f" && echo '{user}:x:1000:' >>/etc/group"
        f" && ksmbd.adduser -a -p {shlex.quote(password)} {user}"
        " && /etc/init.d/ksmbd restart"
    )
    until(
        lambda: module_router.returncode("pidof ksmbd.mountd >/dev/null") == 0,
        timeout=SMB_TIMEOUT,
        what="ksmbd running",
    )
    return SMB_USER


@pytest.fixture(scope="module")
def wireguard(online: Online) -> Iterator[WireGuard]:
    """Connect wg-peer; it routes the LAN and the proxied target through the tunnel."""
    tunnel = WireGuard.connect(online, [LAN_PREFIX, f"{PROXIED_TARGET[0]}/32"])
    yield tunnel
    tunnel.disconnect()


@pytest.fixture(scope="module")
def tailnet(trusted_ca: Online) -> Iterator[Tailnet]:
    """Log the router and ts-peer into headscale."""
    joined = Tailnet.join(trusted_ca)
    yield joined
    joined.leave()
