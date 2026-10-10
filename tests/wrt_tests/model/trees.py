"""Variants of a build or release tree that cost no copies.

The release tests derive many variants of the session's signed build and of its
release, a few hundred megabytes each, and the work directory is on a slow disk
that the emulator's disks share: copying them there stalls the emulated router
while the disk catches up. ``linked_copy`` links a tree's files instead of
copying them, as the Releases stand-in publishes a release (wrt_tests.sandbox.releases);
``replace`` then gives a file of the copy content of its own, leaving the
original, and every other link to it, as it was.
"""

import errno
import os
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _link(source: str, target: str) -> None:
    """Link ``target`` to ``source``, or copy it where the two cannot share a file."""
    try:
        os.link(source, target)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        shutil.copy2(source, target)


def linked_copy(source: Path, target: Path) -> Path:
    """Copy the tree ``source`` to ``target`` as links to its files; return ``target``."""
    shutil.copytree(source, target, copy_function=_link)
    return target


def replace(path: Path, content: bytes | str) -> None:
    """Give ``path`` ``content`` as a file of its own, whatever it was linked to."""
    path.unlink()
    if isinstance(content, str):
        path.write_text(content)
    else:
        path.write_bytes(content)
