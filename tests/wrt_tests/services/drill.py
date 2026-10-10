"""The upgrade drill (r4s-release-pipeline D5): what a bump passes before it may merge.

The router as it booted (in CI's upgrade-drill job the latest stable release,
here this build) gets a configuration pushed with config-push; then it syncs
the signed candidate from the Releases stand-in with wrt-sync, upgrades to it
with wrt-update and reboots into the other slot on trial. The drill passes when
the health check confirms that slot and the configuration is still there; a
candidate that never passes the health check is rolled back after the boot
limit, and the drill fails.
"""

import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from wrt_tests.device.ab import slot
from wrt_tests.device.trust import trust_ca, trust_keys
from wrt_tests.model.repository import REPO_DIR
from wrt_tests.sandbox import releases
from wrt_tests.sandbox.internet import RELEASES

if TYPE_CHECKING:
    from pathlib import Path

    from wrt_tests.device.router import Router
    from wrt_tests.model.keys import Keys
    from wrt_tests.services.datapath import Online

PUBLISH = REPO_DIR / "scripts" / "release-publish.sh"
# The candidate's repository at the Releases stand-in.
REPOSITORY = "wrt-build/drill"
FAILING_CHECK = "/etc/healthcheck.d/99-drill-fails"
# A health check quick enough for a drill that fails (r4s-ab-rollback D4).
HEALTH_LIMITS = {"total": 20, "interval": 5, "timeout": 5}
BOOT_LIMIT = 3
SYNC_TIMEOUT = 600
DRILL_TIMEOUT = 3600
# What the router's own console tells of a drill that ended neither way: the
# slot's state, what still runs (the health check starts after every other
# service), the end of the log and the addresses. CI's run 37126344220 had a
# trial slot that booted and then answered neither ssh nor the drill.
CONSOLE_REPORT = "wrt-slot status; ps w | grep -v ' \\['; logread | tail -n 80; ip -o addr"


@dataclass(frozen=True, slots=True)
class Outcome:
    """How a drill ended: the slot it started from, the slot it ended on, confirmed or not."""

    base_slot: str
    slot: str
    confirmed: bool


def _console_report(router: Router) -> str:
    """Return CONSOLE_REPORT as the router's serial console answers it, or why it does not."""
    try:
        return router.console(CONSOLE_REPORT)
    except Exception as error:  # noqa: BLE001 # a report must not hide the drill's own failure
        return f"(no report: {error!r})"


def _status(router: Router) -> dict[str, str]:
    """Return wrt-slot's status, or nothing while the router cannot be reached."""
    listed = router.poll("wrt-slot status") or ""
    return dict(line.split(": ", 1) for line in listed.splitlines() if ": " in line)


@dataclass
class Drill:
    """A drill of one candidate on the router of ``online``.

    ``candidate`` holds the boards' signed builds, as the sign job hands them on.
    """

    online: Online
    candidate: Path
    keys: Keys | None
    pushed: dict[str, str] = field(default_factory=dict)
    published: str | None = None

    def publish(self, workdir: Path) -> str:
        """Assemble the candidate and put it at the Releases stand-in; return its tag."""
        if self.published is None:
            release = workdir / "candidate"
            boards = ",".join(path.name for path in self.candidate.iterdir())
            subprocess.run(
                [
                    *(PUBLISH, self.candidate, release),
                    *("--boards", boards, "--prerelease", "--run", "drill"),
                ],
                check=True,
                capture_output=True,
            )
            self.published = releases.publish(
                self.online.network.workdir / releases.ROOT, REPOSITORY, release
            )
        return self.published

    def remember(self, **values: str) -> None:
        """Record uci options the configuration push set, to find them after the upgrade."""
        self.pushed.update(values)

    def configuration_kept(self) -> bool:
        """Return whether every recorded option has its pushed value."""
        router = self.online.router
        return all(
            router.run(f"uci -q get {option} || true") == value
            for option, value in self.pushed.items()
        )

    def register_failing_check(self) -> None:
        """Have the candidate's health check fail on every boot (kept through the upgrade)."""
        self.online.router.run(
            f"printf '#!/bin/sh\\nexit 1\\n' >{FAILING_CHECK} && chmod +x {FAILING_CHECK}"
            f" && echo {FAILING_CHECK} >>/etc/sysupgrade.conf"
        )

    def run(self, workdir: Path | None = None) -> Outcome:
        """Sync the candidate, upgrade to it and wait for the confirmation or the rollback."""
        router = self.online.router
        tag = self.publish(workdir or self.candidate.parent)
        base = slot(router)
        # The sandbox's CA is no configuration of the router's, and an earlier
        # drill's upgrade kept none of it.
        trust_ca(router, self.online.network.workdir)
        if self.keys is not None:
            # The slot booted from an image of this build, which trusts the
            # build's own keys: in their place the test's release keys, as a
            # release image trusts the release keys.
            trust_keys(router, self.keys)
        limits = " && ".join(
            f"uci set wrt-ab.healthcheck.{name}={value}" for name, value in HEALTH_LIMITS.items()
        )
        router.run(
            f"{limits} && uci set wrt-sync.main.api=https://{RELEASES[0]}"
            f" && uci set wrt-sync.main.repository={REPOSITORY} && uci commit"
        )
        synced = router.run("wrt-sync --candidate", timeout=SYNC_TIMEOUT)
        assert f"{tag} is current" in synced, synced  # noqa: S101
        console = router.emulator.console
        since = console.mark()
        router.detach("sleep 1; wrt-update")
        # The other slot boots on trial: it is confirmed, or U-Boot rolls back
        # after the boot limit.
        rolled_back = re.compile(rf"Bootlimit \({BOOT_LIMIT}\) exceeded")
        deadline = time.monotonic() + DRILL_TIMEOUT
        while not rolled_back.search(console.text(since)):
            status = _status(router)
            if status.get("slot") not in {None, base} and status.get("state") == "confirmed":
                break
            if time.monotonic() > deadline:
                msg = (
                    f"the drill of {tag} ended neither confirmed nor rolled back;"
                    f" the router's console:\n{_console_report(router)}"
                )
                raise TimeoutError(msg)
            time.sleep(5)
        router.wait_ready()
        self.online.reconnected()
        status = _status(router)
        running = slot(router)
        return Outcome(base, running, running != base and status.get("state") == "confirmed")
