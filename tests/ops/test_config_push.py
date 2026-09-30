"""ops/config-push: the private configuration, encrypted, pushed with config-push.

The module's private repository is config-init's, filled in as an administrator
fills it: the ISP account, WireGuard's key, the tailnet login (a preauth key of
the emulated internet's headscale) and a share user in the encrypted secrets,
the test dae configuration encrypted beside them. It is pushed once to the
module's router, online and trusting the emulated internet, over SSH with the
harness's key; each test pushes what it changed and discards it after. The
upgrade to the other slot comes last.
"""

import hashlib
import subprocess
from dataclasses import dataclass
from secrets import token_urlsafe
from typing import TYPE_CHECKING

import pytest

from wrt_tests import pki, spec
from wrt_tests.config import ConfigRepository
from wrt_tests.datapath import DAE, DAE_CONFIG, hooks
from wrt_tests.isp import LOGIN
from wrt_tests.poll import until
from wrt_tests.vpn import HEADSCALE_URL, clear, key_pair, preauth_key

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from wrt_tests.datapath import Online
    from wrt_tests.router import Router

CAPABILITY = "ops/config-push"
SHARE_USER = {"name": "pushed", "password": "pushed-secret-1"}
# An address the LAN cannot come up with (netifd: INVALID_ADDRESS).
BAD_LAN_ADDRESS = "10.0.0.300/24"
SERVICES = ("dae", "network", "smb", "tailscale")
# The processes the services' reloads restart: dae, the WAN's pppd, the SMB
# server's and tailscaled.
RESTARTED = ("dae", "pppd", "ksmbd.mountd", "tailscaled")
ROOT_PASSWORD = "not-for-config-push"  # noqa: S105 (the test router's, for a password to refuse)
UPGRADE_IMAGE = "/tmp/sysupgrade.tar.gz"  # noqa: S108 (a path on the router)
TAILSCALE_TIMEOUT = 180


@dataclass(frozen=True, slots=True)
class Pushed:
    """The module's repository, pushed to its router, and the secrets pushed."""

    online: Online
    repository: ConfigRepository
    identity: Path
    wireguard_key: str

    @property
    def router(self) -> Router:
        """The router pushed to."""
        return self.online.router

    def push(self) -> subprocess.CompletedProcess[str]:
        """Push the repository as it is now."""
        return self.repository.push(self.router.address, self.identity)


def _state(router: Router) -> dict[str, str]:
    """Return what a push changes on the router, and the processes a reload restarts."""
    return {
        "pushed": router.run("cat /etc/wrt-config/* /etc/dae/* | sha256sum"),
        "uci": router.run("uci export | sha256sum"),
        **{name: router.run(f"pidof {name} || true") for name in RESTARTED},
    }


def _dae_sha256(router: Router) -> str:
    return router.run("sha256sum /etc/dae/config.dae | cut -d' ' -f1")


@pytest.fixture(scope="module")
def pushed(
    trusted_ca: Online, harness_key: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Pushed]:
    """Fill in the repository, push it once, and wait until the tailnet has the router."""
    online = trusted_ca
    network = online.network
    clear(network)
    # tailscaled loads the trusted CAs once: after the test CA came.
    online.router.run("/etc/init.d/tailscale restart")
    repository = ConfigRepository.create(tmp_path_factory.mktemp("config"))
    user, password = LOGIN
    private, _ = key_pair()
    repository.write_secrets(
        {
            "pppoe": {"username": user, "password": password},
            "wireguard": {"private_key": private},
            "tailscale": {"auth_key": preauth_key(network), "login_server": HEADSCALE_URL},
            "smb": {"users": [SHARE_USER]},
        }
    )
    repository.write_dae("config", DAE_CONFIG)
    repository.commit("the router's configuration")
    result = Pushed(online, repository, harness_key, private)
    first = result.push()
    assert first.returncode == 0, first.stderr
    yield result
    clear(network)


@spec(CAPABILITY, "Secrets stored encrypted", "Scan the private repository")
def test_no_secret_in_the_history(pushed: Pushed, tmp_path: Path) -> None:
    def leaks(directory: Path) -> str | None:
        """Return gitleaks' findings in the history of ``directory``, or None."""
        report = tmp_path / f"{directory.name}.json"
        scan = subprocess.run(
            ["gitleaks", "git", "--no-banner", "--report-path", report, directory],
            capture_output=True,
            text=True,
            check=False,
        )
        return None if scan.returncode == 0 else report.read_text() + scan.stderr

    repository = pushed.repository
    assert leaks(repository.directory) is None
    # The scanner does find a secret that went in plain.
    plain = ConfigRepository(tmp_path / "plain", repository.age_key)
    subprocess.run(["git", "clone", "-q", repository.directory, plain.directory], check=True)
    (plain.directory / "secrets" / "pppoe.yaml").write_text(f"password: '{token_urlsafe(16)}'\n")
    plain.commit("a secret in plain text")
    assert leaks(plain.directory) is not None


@spec(CAPABILITY, "Validate before pushing", "Syntax error in dae config")
def test_a_dae_syntax_error_changes_nothing(pushed: Pushed) -> None:
    router = pushed.router
    before = _state(router)
    pushed.repository.write_dae("config", DAE_CONFIG.replace("routing {", "routing {{", 1))
    try:
        result = pushed.push()
    finally:
        pushed.repository.discard()
    assert result.returncode != 0
    assert "dae does not accept the configuration" in result.stderr
    assert "is unchanged" in result.stderr
    assert _state(router) == before
    assert router.returncode("test -e /tmp/wrt-push") != 0


@spec(CAPABILITY, "Repeatable push results", "Repeated push")
def test_a_repeated_push_restarts_nothing(pushed: Pushed) -> None:
    router = pushed.router
    before = _state(router)
    result = pushed.push()
    assert result.returncode == 0, result.stderr
    for service in SERVICES:
        assert f"{service}: unchanged" in result.stderr
    assert _state(router) == before


@spec(CAPABILITY, "Roll back on service failure", "Service reload fails")
def test_a_service_that_fails_is_put_back(pushed: Pushed) -> None:
    router = pushed.router
    before = (router.run("uci get network.lan.ipaddr"), router.run("cat /etc/wrt-config/network"))
    # A batch uci takes but the LAN cannot come up with: without the rollback,
    # the router would be out of reach from the LAN.
    template = pushed.repository.directory / "uci" / "network.uci.tmpl"
    template.write_text(f"{template.read_text()}set network.lan.ipaddr='{BAD_LAN_ADDRESS}'\n")
    try:
        result = pushed.push()
    finally:
        pushed.repository.discard()
        # The LAN was gone for a while, and the harness's connection with it.
        router.disconnect()
    assert result.returncode != 0
    assert "network did not come back with the new configuration" in result.stderr
    assert "the previous one is back" in result.stderr
    assert (
        router.run("uci get network.lan.ipaddr"),
        router.run("cat /etc/wrt-config/network"),
    ) == before
    assert router.run("ubus call network.interface.lan status | jsonfilter -e @.up") == "true"


@spec(CAPABILITY, "dae user config cannot set bind interfaces", "User config sets lan_interface")
def test_lan_interface_is_the_firmware_s(pushed: Pushed) -> None:
    router = pushed.router
    before = _state(router)
    pushed.repository.write_dae(
        "config", DAE_CONFIG.replace("global {\n", "global {\n    lan_interface: br-lan\n", 1)
    )
    try:
        result = pushed.push()
    finally:
        pushed.repository.discard()
    assert result.returncode != 0
    assert "lan_interface and wan_interface are the firmware's" in result.stderr
    assert _state(router) == before


@spec(CAPABILITY, "SSH key authentication only", "No SSH key configured")
def test_no_password_login(pushed: Pushed, tmp_path: Path) -> None:
    router = pushed.router
    # A key the router does not know; root has a password it could log in with.
    unknown = tmp_path / "unknown"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", unknown], check=True)
    router.run(f"printf '%s\\n%s\\n' {ROOT_PASSWORD} {ROOT_PASSWORD} | passwd root >/dev/null")
    passwords = "logread -e 'Bad password' | wc -l"
    before = (_state(router), router.run(passwords))
    try:
        result = pushed.repository.push(router.address, unknown)
    finally:
        router.run("passwd -d root >/dev/null")
    assert result.returncode != 0
    assert "cannot log in" in result.stderr
    # Not one password was tried.
    assert (_state(router), router.run(passwords)) == before


def _tailscale_running(router: Router) -> bool:
    state = router.run("tailscale status --json 2>/dev/null | jsonfilter -e @.BackendState || true")
    return state == "Running"


@spec(CAPABILITY, "Configuration persists across A/B upgrades", "Upgrade to the other slot")
def test_the_configuration_survives_an_upgrade(pushed: Pushed, upgrade_image: Path) -> None:
    router = pushed.router
    until(lambda: _tailscale_running(router), timeout=TAILSCALE_TIMEOUT, what="tailscale up")
    tailnet_address = router.run("tailscale ip -4")
    router.put(upgrade_image, UPGRADE_IMAGE)
    router.reboot(f"sysupgrade {UPGRADE_IMAGE}")
    pushed.online.reconnected()
    # The sandbox's CA is no configuration of the router's, and the upgrade
    # kept none of it: it comes again, and tailscaled, which reads it once, anew.
    pki.trust(router, pushed.online.network.workdir)
    router.run("/etc/init.d/tailscale restart")
    user, password = LOGIN
    assert router.run("uci get network.wan.username") == user
    assert router.run("uci get network.wan.password") == password
    assert router.run("uci get network.wg0.private_key") == pushed.wireguard_key
    assert _dae_sha256(router) == hashlib.sha256(DAE_CONFIG.encode()).hexdigest()
    assert router.run("uci get dae.config.enabled") == "1"
    until(lambda: hooks(router, "br-lan") == DAE, timeout=120, what="dae on br-lan")
    until(lambda: _tailscale_running(router), timeout=TAILSCALE_TIMEOUT, what="tailscale up")
    assert router.run("tailscale ip -4") == tailnet_address
    assert router.returncode(f"grep -q '^{SHARE_USER['name']}:' /etc/ksmbd/ksmbdpwd.db") == 0
    # The new slot knows what was pushed: pushing again changes nothing.
    again = pushed.push()
    assert again.returncode == 0, again.stderr
    for service in SERVICES:
        assert f"{service}: unchanged" in again.stderr
