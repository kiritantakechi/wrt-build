"""The fixtures of every system test, composed from the harness's layers (module-boundaries D6).

Each layer of ``wrt_tests`` provides the fixtures of its domain as a pytest
plugin, from the build under test as data up to the router online; this file
composes them and defines none of its own. A suite's own fixtures live in its
directory's conftest.
"""

pytest_plugins = [
    "wrt_tests.model.fixtures",
    "wrt_tests.sandbox.fixtures",
    "wrt_tests.device.fixtures",
    "wrt_tests.services.fixtures",
]
