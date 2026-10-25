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
import json
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec
from wrt_tests.device.trust import trust_ca
from wrt_tests.model.poll import until
from wrt_tests.sandbox.isp import LOGIN
from wrt_tests.services.config import ConfigRepository
from wrt_tests.services.datapath import DAE, DAE_CONFIG, hooks
from wrt_tests.services.vpn import HEADSCALE_URL, clear, key_pair, preauth_key

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from pathlib import Path

    from wrt_tests.device.router import Router
    from wrt_tests.services.datapath import Online

CAPABILITY = "ops/config-push"
SHARE_USER = {"name": "pushed", "password": "pushed-secret-1"}
# An address the LAN cannot come up with (netifd: INVALID_ADDRESS).
BAD_LAN_ADDRESS = "10.0.0.300/24"
SERVICES = ("dae", "network", "smb", "tailscale")
# The processes the services' reloads restart: dae, the WAN's pppd, the SMB
# server's and tailscaled.
RESTARTED = ("dae", "pppd", "ksmbd.mountd", "tailscaled")
ROOT_PASSWORD = "not-for-config-push"  # noqa: S105 (the test router's, for a password to refuse)
# A password gitleaks' generic rule surely catches in plain text. A random one now
# and then falls short of its entropy threshold, or holds one of its stop words.
PLAIN_SECRET = "vZ8qK3wT9mX2pL7nR4cB"  # noqa: S105  # gitleaks:allow (only scanned for)
UPGRADE_IMAGE = "/tmp/sysupgrade.tar.gz"  # noqa: S108 (a path on the router)
TAILSCALE_TIMEOUT = 180
# Where the router records, while a push runs, the modes of its upload and the
# command lines of its processes.
UPLOAD = "/tmp/wrt-push"  # noqa: S108 (a path on the router)
MODES = "/tmp/push-modes"  # noqa: S108 (a path on the router)
COMMANDS = "/tmp/push-commands"  # noqa: S108 (a path on the router)
WATCH = (
    f"while :; do ls -ldn {UPLOAD} 2>/dev/null; ls -lnR {UPLOAD}/new 2>/dev/null; sleep 0.2;"
    f" done >{MODES} & while :; do for cmdline in /proc/[0-9]*/cmdline; do"
    f" tr '\\0' ' ' <$cmdline; echo; done 2>/dev/null; sleep 0.2; done >{COMMANDS}"
)
# Modes of a file and of a directory that root alone can read.
ROOT_ONLY = ("-rw-------", "drwx------")
# The tailscale CLI: a link to tailscaled, which acts as the CLI by the name it
# runs under. A wrapper in its place records the arguments of every run.
TAILSCALE = "/usr/sbin/tailscale"
TAILSCALE_ARGUMENTS = "/tmp/tailscale-arguments"  # noqa: S108 (a path on the router)
# An auth key headscale refuses.
REFUSED_KEY = "tskey-auth-refused-0000"
# A docroot uhttpd refuses to start with.
NO_DOCROOT = "/nonexistent"


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


def _secrets(pushed: Pushed, auth_key: str) -> dict[str, object]:
    """Return the module's secrets with another Tailscale auth key."""
    user, password = LOGIN
    return {
        "pppoe": {"username": user, "password": password},
        "wireguard": {"private_key": pushed.wireguard_key},
        "tailscale": {"auth_key": auth_key, "login_server": HEADSCALE_URL},
        "smb": {"users": [SHARE_USER]},
    }


@contextmanager
def _recorded_tailscale(router: Router) -> Generator[None]:
    """Have every run of the tailscale CLI record its arguments while the context lasts."""
    real = "/tmp/wrt-test-tailscale"  # noqa: S108 (a path on the router)
    router.run(
        f"mkdir -p {real} && ln -sf /usr/sbin/tailscaled {real}/tailscale"
        f" && cat >{real}/wrapper <<'EOF'\n"
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >>{TAILSCALE_ARGUMENTS}\n'
        f'exec {real}/tailscale "$@"\n'
        "EOF\n"
        f"chmod 755 {real}/wrapper && ln -sf {real}/wrapper {TAILSCALE}"
    )
    try:
        yield
    finally:
        router.run(f"ln -sf tailscaled {TAILSCALE}")


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
    (plain.directory / "secrets" / "pppoe.yaml").write_text(f"password: '{PLAIN_SECRET}'\n")
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
    assert json.loads(router.run("ubus call network.interface.lan status"))["up"] is True


@spec(CAPABILITY, "Secrets stored encrypted", "Secrets on the device")
def test_secrets_on_the_device_are_root_s(pushed: Pushed) -> None:
    router = pushed.router
    auth_key = preauth_key(pushed.online.network)
    pushed.repository.write_secrets(_secrets(pushed, auth_key))
    router.detach(WATCH)
    try:
        with _recorded_tailscale(router):
            result = pushed.push()
    finally:
        router.run(f"pkill -f '{MODES}' || true; pkill -f '{COMMANDS}' || true")
        pushed.repository.commit("another tailnet key")
    assert result.returncode == 0, result.stderr
    # The entries of the listings: a file's line starts with "-", a directory's with "d".
    modes = [
        line.split()[0]
        for line in router.run(f"cat {MODES}").splitlines()
        if line[:1] in {"-", "d"}
    ]
    assert modes
    assert set(modes) <= set(ROOT_ONLY), modes
    assert router.returncode(f"[ -e {UPLOAD} ]") != 0
    files = router.run("ls /etc/dae/* /etc/wrt-config/tailscale.key").split()
    assert {router.run(f"ls -ln {file}").split()[0] for file in files} == {ROOT_ONLY[0]}
    # The key reaches tailscale in its file, and no command line sampled holds it.
    assert "--auth-key=file:" in router.run(f"cat {TAILSCALE_ARGUMENTS}")
    assert auth_key not in router.run(f"cat {TAILSCALE_ARGUMENTS} {COMMANDS}")


@spec(CAPABILITY, "Roll back on service failure", "Tailscale login fails")
def test_a_refused_tailscale_login_is_put_back(pushed: Pushed) -> None:
    router = pushed.router
    until(lambda: _tailscale_running(router), timeout=TAILSCALE_TIMEOUT, what="tailscale up")
    before = (router.run("tailscale ip -4"), router.run("cat /etc/wrt-config/tailscale"))
    pushed.repository.write_secrets(_secrets(pushed, REFUSED_KEY))
    try:
        result = pushed.push()
    finally:
        pushed.repository.discard()
    assert result.returncode != 0
    assert "tailscale did not come back with the new configuration" in result.stderr
    assert "the previous one is back" in result.stderr
    until(lambda: _tailscale_running(router), timeout=TAILSCALE_TIMEOUT, what="tailscale back")
    assert (router.run("tailscale ip -4"), router.run("cat /etc/wrt-config/tailscale")) == before


@spec(CAPABILITY, "Roll back on service failure", "A service that stops with its new configuration")
def test_a_service_that_stops_is_put_back(pushed: Pushed) -> None:
    router = pushed.router
    before = router.run("uci get uhttpd.main.home")
    assert router.returncode("pidof uhttpd >/dev/null") == 0
    template = pushed.repository.directory / "uci" / "uhttpd.uci.tmpl"
    template.write_text(f"set uhttpd.main.home='{NO_DOCROOT}'\n")
    try:
        result = pushed.push()
    finally:
        pushed.repository.discard()
    assert result.returncode != 0
    assert "uhttpd did not come back with the new configuration" in result.stderr
    assert "the previous one is back" in result.stderr
    assert router.run("uci get uhttpd.main.home") == before
    until(
        lambda: router.returncode("pidof uhttpd >/dev/null") == 0,
        timeout=TAILSCALE_TIMEOUT,
        what="uhttpd running",
    )


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
    status = router.run("tailscale status --json 2>/dev/null || true")
    state: object = json.loads(status).get("BackendState") if status else None
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
    trust_ca(router, pushed.online.network.workdir)
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
