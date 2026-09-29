"""services/file-sharing: ksmbd on the LAN only, SMB 3 with a password, shares on the data disk.

smbclient connects from a LAN client, from the internet side, from wg-peer over
WireGuard and from ts-peer over the tailnet; only the LAN gets an answer.
"""

import subprocess
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.poll import until
from wrt_tests.storage import wait_mounted

if TYPE_CHECKING:
    from wrt_tests.datapath import Online
    from wrt_tests.net import Netns
    from wrt_tests.storage import Disk
    from wrt_tests.vpn import Tailnet, WireGuard

CAPABILITY = "services/file-sharing"
SHARE = "shares"
LAN_ADDRESS = "10.0.0.1"
SMB_TIMEOUT = 60


@pytest.fixture(scope="module")
def sharing(online: Online, smb_user: tuple[str, str]) -> Online:
    """Return the router online, sharing the data disk with the test user."""
    del smb_user  # added for the module
    return online


def _smbclient(client: Netns, *args: str) -> tuple[int, str]:
    """Run smbclient (with its defaults, no smb.conf) in ``client``; return status and output."""
    result = subprocess.run(
        client.argv("smbclient", "--configfile=/dev/null", *args),
        capture_output=True,
        text=True,
        check=False,
        timeout=SMB_TIMEOUT,
    )
    return result.returncode, result.stdout + result.stderr


def _list(client: Netns, server: str, user: tuple[str, str], *options: str) -> tuple[int, str]:
    """List ``server``'s shares as ``user``."""
    return _smbclient(client, "--list", f"//{server}", f"--user={user[0]}%{user[1]}", *options)


@spec(CAPABILITY, "LAN-only service", "Access from the LAN")
def test_lan_sees_the_shares(sharing: Online, smb_user: tuple[str, str]) -> None:
    code, output = _list(sharing.client(), LAN_ADDRESS, smb_user)
    assert code == 0, output
    assert SHARE in output.split()
    # The image (/rom) holds no share user: the test added the one there is.
    assert sharing.router.returncode("test -s /rom/etc/ksmbd/ksmbdpwd.db") != 0
    # SMB 3 end to end: into the share.
    code, output = _smbclient(
        sharing.client(),
        f"//{LAN_ADDRESS}/{SHARE}",
        f"--user={smb_user[0]}%{smb_user[1]}",
        "--max-protocol=SMB3",
        "--command=ls",
    )
    assert code == 0, output


@spec(CAPABILITY, "LAN-only service", "Access from the WAN or VPN")
def test_wan_and_vpn_are_refused(
    sharing: Online, smb_user: tuple[str, str], wireguard: WireGuard, tailnet: Tailnet
) -> None:
    for client, server in (
        (sharing.network["inet"], sharing.wan_address),
        (wireguard.peer, LAN_ADDRESS),
        (tailnet.peer, LAN_ADDRESS),
    ):
        code, output = _list(client, server, smb_user)
        assert code != 0
        assert "NT_STATUS_CONNECTION_REFUSED" in output, (client.name, output)


@spec(CAPABILITY, "Authentication required", "Anonymous access")
def test_anonymous_access_is_refused(sharing: Online) -> None:
    for options in (("--no-pass",), ("--user=nobody%guess",)):
        code, output = _smbclient(
            sharing.client(), f"//{LAN_ADDRESS}/{SHARE}", *options, "--command=ls"
        )
        assert code != 0
        assert "NT_STATUS_LOGON_FAILURE" in output or "NT_STATUS_ACCESS_DENIED" in output, output


@spec(CAPABILITY, "Protocol version", "Connect with an SMB 1 client")
def test_smb1_is_refused(sharing: Online, smb_user: tuple[str, str]) -> None:
    code, output = _list(
        sharing.client(),
        LAN_ADDRESS,
        smb_user,
        "--option=client min protocol=NT1",
        "--max-protocol=NT1",
    )
    assert code != 0
    assert "No compatible protocol selected by server" in output, output


@spec(CAPABILITY, "Shares on the data disk", "Data disk absent")
def test_no_shares_without_the_data_disk(
    sharing: Online, smb_user: tuple[str, str], data_disk: Disk
) -> None:
    router = sharing.router
    port = data_disk.port
    assert port is not None
    sharing.reboot(while_off=data_disk.unplug)
    try:
        assert router.returncode("pidof ksmbd.mountd >/dev/null") != 0
        code, output = _list(sharing.client(), LAN_ADDRESS, smb_user)
        assert code != 0
        assert "NT_STATUS_CONNECTION_REFUSED" in output, output
    finally:
        data_disk.plug(port)
        wait_mounted(router)
    until(
        lambda: _list(sharing.client(), LAN_ADDRESS, smb_user)[0] == 0,
        timeout=SMB_TIMEOUT,
        what="the shares back",
    )
