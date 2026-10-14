"""Waiting for a condition, the one way every test waits."""

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def until[T](probe: Callable[[], T | None], *, timeout: float, what: str, every: float = 1) -> T:
    """Call ``probe`` until it answers with content; return that answer.

    An empty answer is no answer yet, as Python's truth testing reads it: None,
    False, zero, an empty string or collection alike, so that a probe means what
    it would mean in a condition. A probe that reports an empty value as its
    result returns something with content instead, such as a comparison.

    A probe that raises stops the wait: probes catch what they expect themselves.
    """
    deadline = time.monotonic() + timeout
    while not (result := probe()):
        if time.monotonic() > deadline:
            msg = f"no {what} within {timeout:g} s"
            raise TimeoutError(msg)
        time.sleep(every)
    return result
