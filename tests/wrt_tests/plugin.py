"""pytest plugin: register the markers and skip tests meant for the other target."""

import pytest

from wrt_tests.markers import TARGET_KINDS


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add ``--target-kind``; scripts/test.sh sets it from the target description."""
    parser.addoption(
        "--target-kind",
        choices=TARGET_KINDS,
        default="emulation",
        help="kind of target the suite runs against (default: emulation)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the markers so that --strict-markers accepts them."""
    config.addinivalue_line(
        "markers", "spec(capability, requirement, scenario): the scenario this test verifies"
    )
    config.addinivalue_line(
        "markers", "target(kind, reason): run only on this kind of target, for this reason"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip, with the stated reason, every test that is meant for the other target."""
    current = config.getoption("--target-kind")
    for item in items:
        mark = item.get_closest_marker("target")
        if mark is None:
            continue
        kind, reason = mark.args
        if kind not in TARGET_KINDS:
            msg = f"{item.nodeid}: unknown target kind {kind!r}"
            raise pytest.UsageError(msg)
        if kind != current:
            item.add_marker(pytest.mark.skip(reason=f"{kind} only: {reason}"))
