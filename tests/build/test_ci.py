"""build/ci: a build hands on its image and kmods with a manifest that describes them.

And the workflows: main's runs delete the caches of merged branches and closed
pull requests, branch runs save caches only within the quota's room, the system
test jobs run every test module once, and runs cancel only what a newer commit
superseded. The cache scripts run against a stand-in gh (wrt_tests.model.github);
the rest reads .github/.
"""

import os
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml

from wrt_tests import spec
from wrt_tests.device.emu import sha256
from wrt_tests.model.boards import load
from wrt_tests.model.github import MAIN, Repository, run_script
from wrt_tests.model.outputs import MANIFEST_FILE

if TYPE_CHECKING:
    from wrt_tests.device.router import Router
    from wrt_tests.model.outputs import Manifest

CAPABILITY = "build/ci"
REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "build.yml"
NIX = REPO / ".github" / "actions" / "nix" / "action.yml"
TESTS = REPO / "tests"
IMAGES = ("targets/*-factory.img.gz", "targets/*-sysupgrade.tar.gz")
KMODS = "targets/packages/packages.adb"
MIB = 1024 * 1024
# How a test names a document it reads: the path "docs", then its name.
DOCUMENT = re.compile(r'"docs"\s*/\s*"([^"]+)"')


def _workflow(path: Path = WORKFLOW) -> dict[str, Any]:
    return cast("dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8")))


def _triggers(path: Path = WORKFLOW) -> dict[str, Any]:
    """Return a workflow's events, its key ``on``, which YAML 1.1 reads as true."""
    return cast("dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8"))[True])


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


@spec(CAPABILITY, "Image and kmods from the same build", "Complete manifest")
def test_the_manifest_describes_the_build(
    router: Router, build_output: Path, manifest: Manifest
) -> None:
    files = manifest.files
    assert manifest.run
    assert manifest.upstream_lock_sha256 == sha256(REPO / "upstream.lock")
    # It lists every other file of the build, each by its path in it.
    held = {
        path.relative_to(build_output).as_posix()
        for path in build_output.rglob("*")
        if path.is_file() and path.name != MANIFEST_FILE
    }
    assert files.keys() == held
    # It names the board the images were built for, and its device, after which
    # OpenWrt names them.
    device = load(manifest.board).device
    assert manifest.device == device
    images = [path for pattern in IMAGES for path in build_output.glob(pattern)]
    assert len(images) == len(IMAGES)
    for image in images:
        assert f"-{device}-" in image.name
        assert files[image.relative_to(build_output).as_posix()] == sha256(image)
    assert files[KMODS] == sha256(build_output / KMODS)
    # Its vermagic is the one of the image's kernel and of every kmod.
    vermagic = f"~{manifest.vermagic}-"
    assert vermagic in router.run("apk list -I kernel")
    index = subprocess.run(
        ["apk", "adbdump", build_output / KMODS], capture_output=True, text=True, check=True
    ).stdout
    kernels = set(re.findall(r"kernel=([^\s\"']+)", index))
    assert kernels
    assert all(vermagic in kernel for kernel in kernels), kernels


@spec(CAPABILITY, "Main's caches kept whole", "A merged branch")
def test_main_deletes_merged_branches_caches(tmp_path: Path) -> None:
    compare = {
        "merged": "behind",
        "identical": "identical",
        "ahead": "ahead",
        "diverged": "diverged",
    }
    repository = Repository(branches=["main", *compare], compare=compare, pulls={"1": "open"})
    for branch in (*compare, "deleted"):
        repository.cache(f"refs/heads/{branch}", f"dl-{branch}")
    repository.cache("refs/pull/1/merge", "dl-pull")
    repository.cache(MAIN, "toolchain-1")
    # The caches job of main's run (scripts/cache-prune.sh).
    result, left = run_script(tmp_path, repository, "cache-prune.sh", "toolchain-1", ref=MAIN)
    assert result.returncode == 0, result.stderr
    # A branch merged into main, or one deleted, keeps no cache; the others stay.
    assert sorted(ref for ref, _ in left) == [
        "refs/heads/ahead",
        "refs/heads/diverged",
        MAIN,
        "refs/pull/1/merge",
    ]


@spec(CAPABILITY, "Main's caches kept whole", "A closed pull request")
def test_main_deletes_closed_pull_requests_caches(tmp_path: Path) -> None:
    repository = Repository(pulls={"1": "closed", "2": "open"})
    for number in repository.pulls:
        repository.cache(f"refs/pull/{number}/merge", f"dl-{number}")
    repository.cache(MAIN, "toolchain-1")
    result, left = run_script(tmp_path, repository, "cache-prune.sh", "toolchain-1", ref=MAIN)
    assert result.returncode == 0, result.stderr
    assert sorted(ref for ref, _ in left) == [MAIN, "refs/pull/2/merge"]


@spec(CAPABILITY, "Cache keyed on actual inputs", "Stage names with a hyphen")
def test_a_stage_named_with_a_hyphen_keeps_its_newest_cache(tmp_path: Path) -> None:
    repository = Repository()
    repository.cache(MAIN, "toolchain-1")
    for run in ("1", "2"):
        for stage in ("r6s", "r6s-plus"):
            repository.cache(MAIN, f"compiler-cache-{stage}-settings-{run}")
    result, left = run_script(tmp_path, repository, "cache-prune.sh", "toolchain-1", ref=MAIN)
    assert result.returncode == 0, result.stderr
    assert sorted(key for _, key in left) == [
        "compiler-cache-r6s-plus-settings-2",
        "compiler-cache-r6s-settings-2",
        "toolchain-1",
    ]


@spec(CAPABILITY, "Main's caches kept whole", "Room for the jobs that save at once")
@pytest.mark.parametrize(("savers", "save"), [("1", "true"), ("2", "false")])
def test_room_counts_every_job_that_saves(tmp_path: Path, savers: str, save: str) -> None:
    # Each board's job asks for its caches together, counted for every board's.
    firmware = _workflow()["jobs"]["firmware"]
    room = _step(firmware, "Room for the caches")
    assert room["env"]["CACHE_SAVERS"] == "${{ strategy.job-total }}"
    assert '"$WRT_WORKDIR/dl" "$WRT_WORKDIR/compiler-cache"' in room["run"]
    for name in ("Save download cache", "Save compiler cache"):
        assert "steps.room.outputs.save == 'true'" in _step(firmware, name)["if"]
    # Room for one board's cache, not for two.
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "entry").write_bytes(os.urandom(MIB))
    repository = Repository()
    repository.cache(MAIN, "dl-main", 5 * MIB // 2)
    result, _ = run_script(
        tmp_path,
        repository,
        "cache-room.sh",
        str(cache),
        ref="refs/heads/feature",
        CACHE_QUOTA=str(4 * MIB),
        CACHE_SAVERS=savers,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"save={save}\n"


@spec(CAPABILITY, "Main's caches kept whole", "A job that fails before its downloads end")
def test_a_download_cache_follows_every_download() -> None:
    firmware = _workflow()["jobs"]["firmware"]
    steps = firmware["steps"]
    download = next(step for step in steps if step.get("id") == "download")
    assert download["run"] == "nix develop .#build -c just download"
    # The downloads end before the build starts, and the cache is saved only
    # when they all succeeded, whatever the build did.
    assert steps.index(download) < steps.index(_step(firmware, "Build firmware"))
    save = _step(firmware, "Save download cache")
    assert save["if"].startswith("always() && steps.download.outcome == 'success' && ")


@spec(CAPABILITY, "Workflows cancel only their own superseded runs", "Re-run of an older run")
def test_a_rerun_waits_for_the_newer_run() -> None:
    concurrency = _workflow()["concurrency"]
    assert concurrency["group"] == "build-${{ github.ref }}"
    assert concurrency["cancel-in-progress"] == "${{ github.run_attempt == '1' }}"


@spec(CAPABILITY, "Workflows cancel only their own superseded runs", "Weekly audit and a push")
def test_the_weekly_audit_and_a_push_run_apart() -> None:
    check = WORKFLOWS / "check.yml"
    assert {"push", "schedule"} <= _triggers(check).keys()
    assert "${{ github.event_name }}" in _workflow(check)["concurrency"]["group"]


def _documents_tests_read() -> list[str]:
    return sorted(
        {
            f"docs/{name}"
            for module in TESTS.rglob("*.py")
            for name in DOCUMENT.findall(module.read_text(encoding="utf-8"))
        }
    )


@spec(CAPABILITY, "Documents that tests read run the tests", "A document a test reads")
@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_a_document_a_test_reads_runs_the_build(event: str) -> None:
    documents = _documents_tests_read()
    assert documents
    paths = _triggers()[event]["paths"]
    assert paths[paths.index("!**/*.md") + 1 :] == documents


@spec(CAPABILITY, "Documents that tests read run the tests", "A document no test reads")
@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_other_documentation_does_not_run_the_build(event: str) -> None:
    paths = _triggers()[event]["paths"]
    # GitHub reads the patterns in order, the last that matches deciding: code
    # runs the build, then documentation does not, then the documents tests read
    # do again.
    assert paths[: paths.index("!**/*.md") + 1] == ["**", "!openspec/**", "!docs/**", "!**/*.md"]


@spec(CAPABILITY, "One pinned Nix in every job", "Installer of every job")
def test_every_job_installs_the_one_pinned_nix() -> None:
    (installer,) = [
        step
        for step in yaml.safe_load(NIX.read_text(encoding="utf-8"))["runs"]["steps"]
        if "uses" in step
    ]
    assert installer["uses"].startswith("DeterminateSystems/nix-installer-action@")
    assert re.fullmatch(r"v\d+\.\d+\.\d+", installer["with"]["source-tag"])
    for path in WORKFLOWS.glob("*.yml"):
        for name, job in _workflow(path)["jobs"].items():
            steps = job.get("steps", [])
            uses = [step.get("uses", "") for step in steps]
            assert not any("nix" in use.lower() for use in uses if use != "./.github/actions/nix")
            runs_nix = any(re.search(r"\bnix\b", step.get("run", "")) for step in steps)
            assert runs_nix == ("./.github/actions/nix" in uses), f"{path.name}: {name}"


def _modules(path: Path) -> list[Path]:
    """Return the test modules a suite's path selects: a directory's, or the module itself."""
    assert path.exists(), f"a suite names {path.relative_to(TESTS)}, which does not exist"
    return sorted(path.glob("test_*.py")) if path.is_dir() else [path]


@spec(CAPABILITY, "System tests within job time limits", "Every test in one job")
def test_every_test_module_runs_in_one_job() -> None:
    jobs = _workflow()["jobs"]
    suites = jobs["system-test"]["strategy"]["matrix"]["suite"]
    selected = Counter(
        module.relative_to(TESTS).as_posix()
        for suite in suites
        for path in suite["paths"].split()
        for module in _modules(TESTS / path)
    )
    modules = {module.relative_to(TESTS).as_posix() for module in TESTS.glob("*/test_*.py")}
    assert sorted(modules - selected.keys()) == [], "test modules no suite runs"
    assert sorted(name for name, count in selected.items() if count > 1) == [], "run twice"
