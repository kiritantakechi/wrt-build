"""firmware/health-check: LAN, SSH, the web UI and every registered check make a healthy boot."""

import json
import re
from typing import TYPE_CHECKING, cast

from wrt_tests import spec
from wrt_tests.device.ab import getenv, setenv, slot

if TYPE_CHECKING:
    from wrt_tests.device.router import Router

CAPABILITY = "firmware/health-check"
RESULT = "/var/run/wrt-healthcheck.json"
CHECKS = "/etc/healthcheck.d"
FAILING = "/tmp/demo-fails"  # noqa: S108 (a path on the router)
# Limits short enough for a test and long enough for a check to fail twice.
LIMITS = {"total": 6, "interval": 3, "timeout": 3}
QUICK = " && ".join(f"uci set wrt-ab.healthcheck.{name}={value}" for name, value in LIMITS.items())


def _check(router: Router) -> dict[str, object]:
    """Run the health check with short limits and return its recorded result."""
    router.run(f"{QUICK} && uci commit wrt-ab && wrt-healthcheck", timeout=120)
    return cast("dict[str, object]", json.loads(router.run(f"cat {RESULT}")))


def _register(router: Router, name: str, body: str) -> None:
    """Install a registered check."""
    router.run(f"printf '#!/bin/sh\\n%s\\n' '{body}' > {CHECKS}/{name} && chmod +x {CHECKS}/{name}")


@spec(CAPABILITY, "Built-in checks", "WAN down, everything else healthy")
def test_wan_is_not_a_criterion(router: Router) -> None:
    router.run("ifdown wan")
    assert router.run("ifstatus wan | jsonfilter -e '@.up'") == "false"
    result = _check(router)
    assert (result["result"], result["failed"]) == ("pass", [])


@spec(CAPABILITY, "Built-in checks", "Web server not up")
def test_web_server_down_fails(router: Router) -> None:
    router.run("/etc/init.d/uhttpd stop")
    result = _check(router)
    assert (result["result"], result["failed"]) == ("fail", ["web"])


@spec(CAPABILITY, "Components can register checks", "Registered check fails")
def test_failing_registered_check(router: Router) -> None:
    _register(router, "demo", "exit 1")
    result = _check(router)
    assert (result["result"], result["failed"]) == ("fail", ["demo"])


@spec(CAPABILITY, "Components can register checks", "Check times out")
def test_slow_registered_check(router: Router) -> None:
    _register(router, "slow", "sleep 600")
    result = _check(router)
    assert (result["result"], result["failed"]) == ("fail", ["slow"])


@spec(CAPABILITY, "Result handling by trial boot state", "Check passes during trial boot")
def test_pass_confirms_the_slot(router: Router) -> None:
    running = slot(router)
    setenv(router, boot_slot=running, upgrade_available=1, bootcount=2)
    assert _check(router)["result"] == "pass"
    assert (getenv(router, "upgrade_available"), getenv(router, "bootcount")) == ("0", "0")
    router.reboot()
    assert slot(router) == running


@spec(CAPABILITY, "Result handling by trial boot state", "Check fails during trial boot")
def test_trial_failure_reboots(router: Router) -> None:
    running = slot(router)
    setenv(router, boot_slot=running, upgrade_available=1, bootcount=0)
    # Fails for this boot only: /tmp starts empty, so the next boot passes and confirms.
    router.run(f"touch {FAILING}")
    _register(router, "demo", f"[ ! -e {FAILING} ]")
    previous_boot = router.boot_id()
    router.detach(f"{QUICK} && uci commit wrt-ab && wrt-healthcheck")
    router.wait_rebooted(previous_boot)
    confirmed = f"slot {running} passed its trial boot and is confirmed"
    router.run(
        f"until logread -e wrt-healthcheck | grep -q '{confirmed}'; do sleep 2; done", timeout=300
    )


@spec(CAPABILITY, "Result handling by trial boot state", "Check fails on a confirmed system")
def test_confirmed_failure_only_records(router: Router) -> None:
    assert getenv(router, "upgrade_available") in {None, "0"}
    _register(router, "demo", "exit 1")
    previous_boot = router.boot_id()
    assert _check(router)["result"] == "fail"
    assert router.boot_id() == previous_boot
    assert router.returncode("logread -e wrt-healthcheck | grep -q 'is unhealthy: demo'") == 0


@spec(CAPABILITY, "Slot status query", "Query status")
def test_slot_status(router: Router) -> None:
    _register(router, "demo", "exit 1")
    _check(router)
    status = dict(line.split(": ", 1) for line in router.run("wrt-slot status").splitlines())
    assert status["slot"] == slot(router)
    assert status["state"] == "confirmed"
    assert re.fullmatch(
        r"fail at \d{4}-\d\d-\d\d \d\d:\d\d:\d\d \(failed: demo\)", status["health"]
    )
