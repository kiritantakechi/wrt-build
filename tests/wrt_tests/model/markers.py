"""The markers of the system tests (design D13), and the pytest plugin that registers them.

``@spec`` names the scenario a test verifies; ``drill`` marks the upgrade drill,
which CI's upgrade-drill job runs (r4s-release-pipeline D5). ``tests/pytest.toml``
loads this module as a plugin, so that ``--strict-markers`` accepts both.
"""

# A runtime import: pluggy evaluates the annotations of hook implementations.
import pytest


def spec(capability: str, requirement: str, scenario: str) -> pytest.MarkDecorator:
    """Mark a test as the test of one spec scenario."""
    return pytest.mark.spec(capability, requirement, scenario)


def pytest_configure(config: pytest.Config) -> None:
    """Register the markers so that --strict-markers accepts them."""
    config.addinivalue_line(
        "markers", "spec(capability, requirement, scenario): the scenario this test verifies"
    )
    config.addinivalue_line(
        "markers", "drill: the upgrade drill, CI's upgrade-drill job (r4s-release-pipeline D5)"
    )
