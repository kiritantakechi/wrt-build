"""pytest plugin: register the ``spec`` and ``drill`` markers."""

# A runtime import: pluggy evaluates the annotations of hook implementations.
import pytest  # noqa: TC002


def pytest_configure(config: pytest.Config) -> None:
    """Register the markers so that --strict-markers accepts them."""
    config.addinivalue_line(
        "markers", "spec(capability, requirement, scenario): the scenario this test verifies"
    )
    config.addinivalue_line(
        "markers", "drill: the upgrade drill, CI's upgrade-drill job (r4s-release-pipeline D5)"
    )
