"""pytest plugin: register the ``spec`` marker."""

# A runtime import: pluggy evaluates the annotations of hook implementations.
import pytest  # noqa: TC002


def pytest_configure(config: pytest.Config) -> None:
    """Register the marker so that --strict-markers accepts it."""
    config.addinivalue_line(
        "markers", "spec(capability, requirement, scenario): the scenario this test verifies"
    )
