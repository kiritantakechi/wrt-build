"""Fixtures of the release tests: the upgrade drill (r4s-release-pipeline D5).

The drill's router is online, resolves and trusts the emulated internet, and
has a data disk for its local repository. Before the drill it gets the test
configuration an administrator would push: the ISP account, dae, WireGuard's
key and a share user, with config-push from a private repository of the test's
own; the drill checks that it is still there on the upgraded slot.
"""

from typing import TYPE_CHECKING

import pytest

from wrt_tests.sandbox.isp import LOGIN
from wrt_tests.services.config import ConfigRepository
from wrt_tests.services.datapath import DAE_CONFIG
from wrt_tests.services.drill import Drill
from wrt_tests.services.vpn import key_pair

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.device.storage import Disk
    from wrt_tests.model.keys import Keys
    from wrt_tests.services.datapath import Online

SHARE_USER = {"name": "drill", "password": "drill-secret-1"}


@pytest.fixture(scope="module")
def drill_configuration(
    trusted_ca: Online, harness_key: Path, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, str]:
    """Push the drill's configuration; return the uci options it set."""
    repository = ConfigRepository.create(tmp_path_factory.mktemp("drill"))
    user, password = LOGIN
    private, _ = key_pair()
    repository.write_secrets(
        {
            "pppoe": {"username": user, "password": password},
            "wireguard": {"private_key": private},
            "smb": {"users": [SHARE_USER]},
        }
    )
    repository.write_dae("config", DAE_CONFIG)
    repository.commit("the drill's configuration")
    pushed = repository.push(trusted_ca.router.address, harness_key)
    assert pushed.returncode == 0, pushed.stderr  # noqa: S101
    return {
        "network.wan.username": user,
        "network.wan.password": password,
        "network.wg0.private_key": private,
        "dae.config.enabled": "1",
    }


@pytest.fixture(scope="module")
def drill(
    trusted_ca: Online,
    drill_configuration: dict[str, str],
    data_disk: Disk,
    signed_boards: Path,
    release_keys: Keys | None,
) -> Drill:
    """Return the drill of the signed build on the configured router."""
    del data_disk  # the local repository's place
    drill = Drill(trusted_ca, signed_boards, release_keys)
    drill.remember(**drill_configuration)
    return drill
