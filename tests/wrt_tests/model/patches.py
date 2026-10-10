"""The patch files of the repository and their upstream status (docs/patches.md)."""

import re
import subprocess

from wrt_tests.model.repository import REPO_DIR

DOC = REPO_DIR / "docs" / "patches.md"
# OpenEmbedded's vocabulary (docs/patches.md).
STATUS = re.compile(r"Pending|Submitted \[.+\]|Backport \[.+\]|Inappropriate \[.+\]")
MEANT_FOR_UPSTREAM = ("Pending", "Submitted")
TRAILER = re.compile(r"^([A-Za-z][A-Za-z0-9-]*): (.+)$")


def upstream_status(text: str) -> str | None:
    """Return the Upstream-Status trailer of a patch file's text, or None.

    A git format-patch file carries it at the end of its message, before the
    ``---`` line; a plain diff in its header, before the diff itself.
    """
    if text.startswith("From ") and "\n---\n" in text:
        message = text.split("\n---\n", 1)[0]
        part = message.rstrip("\n").split("\n\n")[-1]
    else:
        part = re.split(r"(?m)^(?:diff |--- |Index: )", text, maxsplit=1)[0]
    found: list[str] = [
        match.group(2)
        for line in part.splitlines()
        if (match := TRAILER.match(line)) and match.group(1) == "Upstream-Status"
    ]
    return found[-1] if found else None


def write_ups(doc: str) -> dict[str, str]:
    """Return the write-ups of the patch documentation: each title and the patch file it names."""
    section = doc.split("\n## Patches meant for upstream\n", 1)[-1]
    found: dict[str, str] = {}
    for block in re.split(r"(?m)^### ", section)[1:]:
        title, _, body = block.partition("\n")
        named = re.search(r"(?m)^Patch: `([^`]+)`", body)
        found[title.strip()] = named.group(1) if named else ""
    return found


def unstated(patches: dict[str, str | None]) -> list[str]:
    """Return the patches without a status in the vocabulary."""
    return [
        path for path, status in patches.items() if status is None or not STATUS.fullmatch(status)
    ]


def without_write_up(patches: dict[str, str | None], titles: dict[str, str]) -> list[str]:
    """Return the patches meant for upstream that no write-up names."""
    named = set(titles.values())
    return [
        path
        for path, status in patches.items()
        if status and status.split(" ")[0] in MEANT_FOR_UPSTREAM and path not in named
    ]


def without_patch(patches: dict[str, str | None], titles: dict[str, str]) -> list[str]:
    """Return the write-ups that name no patch meant for upstream."""
    return [
        title
        for title, path in titles.items()
        if (patches.get(path) or "").split(" ")[0] not in MEANT_FOR_UPSTREAM
    ]


def repository_patches() -> dict[str, str | None]:
    """Return every patch file of the repository and its status."""
    listed = subprocess.run(
        ["git", "-C", str(REPO_DIR), "ls-files", "-z", "*.patch", "*.diff"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {
        path: upstream_status((REPO_DIR / path).read_text())
        for path in sorted(listed.split("\0"))
        if path
    }
