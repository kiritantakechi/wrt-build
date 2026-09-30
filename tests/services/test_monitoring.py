"""services/monitoring: the ucode node exporter on the LAN, with or without a data disk.

The module's router has no data disk, so every scrape also shows that metrics
need none.
"""

import re
from typing import TYPE_CHECKING

import pytest

from wrt_tests import spec

if TYPE_CHECKING:
    from wrt_tests.datapath import Online

CAPABILITY = "services/monitoring"
LAN_ADDRESS = "10.0.0.1"
PORT = 9101
URL = f"http://{LAN_ADDRESS}:{PORT}/metrics"


@pytest.fixture(scope="module")
def metrics(online: Online) -> str:
    """Scrape the router from a LAN client."""
    return online.client().run("curl", "--silent", "--fail", "--max-time", "30", URL)


def _series(metrics: str, name: str) -> list[str]:
    return [line for line in metrics.splitlines() if re.match(rf"{name}[{{ ]", line)]


@spec(CAPABILITY, "Metrics exported on the LAN", "Scrape from the LAN")
def test_scrape_from_the_lan(metrics: str) -> None:
    assert "# TYPE node_cpu_seconds_total counter" in metrics
    for name in (
        "node_cpu_seconds_total",
        "node_memory_MemTotal_bytes",
        "node_network_receive_bytes_total",
        "node_filesystem_size_bytes",
    ):
        assert _series(metrics, name), name
    assert any(
        'device="br-lan"' in line for line in _series(metrics, "node_network_receive_bytes_total")
    )


@spec(CAPABILITY, "Metrics exported on the LAN", "Temperature metrics")
def test_temperature_metrics(online: Online, metrics: str) -> None:
    assert re.search(
        r'^node_scrape_collector_success\{collector="hwmon"\} 1$', metrics, re.MULTILINE
    )
    # The sensor driver of both SoCs is in the kernel; on a board it feeds hwmon.
    assert online.router.returncode("test -d /sys/bus/platform/drivers/rockchip-thermal") == 0


@spec(CAPABILITY, "Metrics exported on the LAN", "Access from the WAN")
def test_wan_is_refused(online: Online) -> None:
    probe = online.network["inet"].probe("connect", online.wan_address, "--port", str(PORT))
    assert probe == {"connection": "refused"}


@spec(CAPABILITY, "Independent of the data disk", "No data disk attached")
def test_no_data_disk_attached(online: Online, metrics: str) -> None:
    assert online.router.returncode("grep -q ' /mnt/data ' /proc/mounts") != 0
    overlay = [
        line
        for line in _series(metrics, "node_filesystem_size_bytes")
        if 'mountpoint="/overlay"' in line
    ]
    assert overlay, _series(metrics, "node_filesystem_size_bytes")
    assert float(overlay[0].rsplit(" ", 1)[1]) > 0
