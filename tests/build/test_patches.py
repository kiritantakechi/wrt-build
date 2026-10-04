"""build/upstream-pinning: every patch states its upstream status, with write-ups in step."""

import re
import subprocess
from pathlib import Path

from wrt_tests import spec

CAPABILITY = "build/upstream-pinning"
REQUIREMENT = "Every patch states its upstream status"
REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "patches.md"
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


def _repository_patches() -> dict[str, str | None]:
    listed = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "*.patch", "*.diff"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {
        path: upstream_status((REPO / path).read_text())
        for path in sorted(listed.split("\0"))
        if path
    }


@spec(CAPABILITY, REQUIREMENT, "Patch without a status")
def test_every_patch_states_its_status() -> None:
    patches = _repository_patches()
    assert patches
    assert unstated(patches) == []


@spec(CAPABILITY, REQUIREMENT, "Patch meant for upstream without a write-up")
def test_patches_meant_for_upstream_have_their_write_ups() -> None:
    assert without_write_up(_repository_patches(), write_ups(DOC.read_text())) == []


@spec(CAPABILITY, REQUIREMENT, "Write-up without a patch")
def test_every_write_up_names_its_patch() -> None:
    assert without_patch(_repository_patches(), write_ups(DOC.read_text())) == []


def test_the_trailer_is_read_from_either_kind_of_patch() -> None:
    format_patch = (
        "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
        "From: a <a@b>\nSubject: [PATCH] fix\n\nWhy.\n\n"
        "Signed-off-by: a <a@b>\nUpstream-Status: Pending\n---\n f | 1 +\n\ndiff --git a/f b/f\n"
    )
    plain = "Why.\n\nUpstream-Status: Backport [upstream 1234abc]\n\n--- a/f\n+++ b/f\n"
    in_the_diff = "Why.\n\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n+Upstream-Status: Pending\n"
    assert upstream_status(format_patch) == "Pending"
    assert upstream_status(plain) == "Backport [upstream 1234abc]"
    assert upstream_status(in_the_diff) is None


def test_the_checks_name_what_is_wrong() -> None:
    patches = {
        "no-trailer.patch": None,
        "unknown.patch": "Upstream",
        "pending.patch": "Pending",
        "submitted.patch": "Submitted [https://example.org/pull/1]",
        "local.patch": "Inappropriate [this project only]",
    }
    titles = {"Submitted": "submitted.patch", "Stray": "gone.patch", "Local": "local.patch"}
    assert unstated(patches) == ["no-trailer.patch", "unknown.patch"]
    assert without_write_up(patches, titles) == ["pending.patch"]
    assert without_patch(patches, titles) == ["Stray", "Local"]
