"""The patch checks of tests/wrt_tests/model/patches.py, on made-up patches and write-ups."""

from wrt_tests.model.patches import unstated, upstream_status, without_patch, without_write_up


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
