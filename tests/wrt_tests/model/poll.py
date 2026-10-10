"""Waiting for a condition, the one way every test waits."""

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def until[T](probe: Callable[[], T | None], *, timeout: float, what: str, every: float = 1) -> T:
    """Call ``probe`` until it returns something other than None or False; return that.

    A probe that raises stops the wait: probes catch what they expect themselves.
    """
    deadline = time.monotonic() + timeout
    while (result := probe()) is None or result is False:
        if time.monotonic() > deadline:
            msg = f"no {what} within {timeout:g} s"
            raise TimeoutError(msg)
        time.sleep(every)
    return result
