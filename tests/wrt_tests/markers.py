"""The marker every system test carries (design D13): ``@spec`` names its scenario."""

import pytest


def spec(capability: str, requirement: str, scenario: str) -> pytest.MarkDecorator:
    """Mark a test as the test of one spec scenario."""
    return pytest.mark.spec(capability, requirement, scenario)
