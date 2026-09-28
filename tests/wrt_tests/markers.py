"""The two markers every system test uses (design D13).

``@spec`` names the one scenario a test verifies. ``@target`` restricts a test to
one kind of target and says why; unmarked tests run on both.
"""

from typing import Literal

import pytest

type TargetKind = Literal["emulation", "device"]
TARGET_KINDS: tuple[TargetKind, ...] = ("emulation", "device")


def spec(capability: str, requirement: str, scenario: str) -> pytest.MarkDecorator:
    """Mark a test as the test of one spec scenario."""
    return pytest.mark.spec(capability, requirement, scenario)


def target(kind: TargetKind, reason: str) -> pytest.MarkDecorator:
    """Run a test only on one kind of target; ``reason`` is shown when it is skipped."""
    return pytest.mark.target(kind, reason)
