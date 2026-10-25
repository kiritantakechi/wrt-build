"""Unit tests of scripts/cache-room.sh and scripts/cache-prune.sh against a stand-in gh."""

import os
from typing import TYPE_CHECKING

import pytest

from wrt_tests.model.github import MAIN, Repository, run_script

if TYPE_CHECKING:
    from pathlib import Path

MIB = 1024 * 1024


@pytest.mark.parametrize(
    ("ref", "used", "save"),
    [
        pytest.param(MAIN, 4 * MIB, "true", id="default branch, full"),
        pytest.param("refs/heads/feature", 1 * MIB, "true", id="branch, room"),
        pytest.param("refs/heads/feature", 7 * MIB // 2, "false", id="branch, no room"),
        pytest.param("refs/pull/1/merge", 7 * MIB // 2, "false", id="pull request, no room"),
    ],
)
def test_room_for_a_cache(tmp_path: Path, ref: str, used: int, save: str) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "entry").write_bytes(os.urandom(MIB))
    repository = Repository()
    repository.cache(MAIN, "dl-main", used)
    result, _ = run_script(
        tmp_path, repository, "cache-room.sh", str(cache), ref=ref, CACHE_QUOTA=str(4 * MIB)
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"save={save}\n"


def _caches_of_two_runs(repository: Repository, ref: str) -> None:
    """Add the caches two runs on ``ref`` leave, the second's newer."""
    for run in ("1", "2"):
        repository.cache(ref, f"toolchain-{run}")
        repository.cache(ref, f"dl-{run}")
        for stage in ("host", "r4s"):
            repository.cache(ref, f"compiler-cache-{stage}-settings-{run}")


def test_a_run_prunes_what_it_superseded(tmp_path: Path) -> None:
    repository = Repository(branches=["main", "feature"], compare={"feature": "ahead"})
    _caches_of_two_runs(repository, "refs/heads/feature")
    # main's caches under the same keys stay: caches go by id.
    _caches_of_two_runs(repository, MAIN)
    result, left = run_script(
        tmp_path, repository, "cache-prune.sh", "toolchain-2", ref="refs/heads/feature"
    )
    assert result.returncode == 0, result.stderr
    assert sorted(key for ref, key in left if ref == "refs/heads/feature") == [
        "compiler-cache-host-settings-2",
        "compiler-cache-r4s-settings-2",
        "dl-2",
        "toolchain-2",
    ]
    assert len([ref for ref, _ in left if ref == MAIN]) == len(repository.caches) // 2


def test_a_branch_leaves_other_branches_caches(tmp_path: Path) -> None:
    repository = Repository(branches=["main", "feature"], compare={"feature": "ahead"})
    repository.cache("refs/heads/deleted", "dl-deleted")
    repository.cache("refs/heads/feature", "toolchain-1")
    result, left = run_script(
        tmp_path, repository, "cache-prune.sh", "toolchain-1", ref="refs/heads/feature"
    )
    assert result.returncode == 0, result.stderr
    assert sorted(ref for ref, _ in left) == ["refs/heads/deleted", "refs/heads/feature"]
