"""release/signing: a job of its own signs with keys only it sees; devices trust only them.

The workflow checks read .github/workflows, and run the sign job's script with a
stand-in nix that records what it would sign. Signing runs
scripts/release-sign.sh, the script the sign job runs, with the session's release
keys; the router trusts those keys (conftest), as a release image trusts the
production ones.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml

from wrt_tests import spec
from wrt_tests.device.emu import sha256
from wrt_tests.model.boards import load_all
from wrt_tests.model.data import read_json, write_json
from wrt_tests.model.keys import APK_KEYS, FIRMWARE_KEYS, Keys, sign
from wrt_tests.model.outputs import MANIFEST_FILE, Manifest
from wrt_tests.model.trees import linked_copy, replace
from wrt_tests.sandbox.oci import extract_root

if TYPE_CHECKING:
    from wrt_tests.device.router import Router
    from wrt_tests.model.outputs import EmulationSource

CAPABILITY = "release/signing"
REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
KEYRING = REPO / "feed" / "utils" / "wrt-keyring" / "files"
SECRETS = ("RELEASE_APK_KEY", "RELEASE_FW_KEY")
ENVIRONMENT = "release-signing"
INDEX = "targets/packages/packages.adb"
ON_ROUTER = "/tmp/packages.adb"  # noqa: S108 (a path on the router)
# The only actions the sign job may use: the checkout, the pinned Nix and the
# artifacts.
SIGN_ACTIONS = {"actions/checkout", "./.github/actions/nix"} | {
    f"actions/{verb}-artifact" for verb in ("download", "upload")
}
# A board of boards/, whose build the sign job tests sign.
BOARD = load_all()[0].id
# What signing adds to a build's files.
SIGNING = {MANIFEST_FILE, f"{MANIFEST_FILE}.sig", "SHA256SUMS"}
# A stand-in for nix that records its arguments, one call per line.
NIX = """#!/bin/sh
printf '%s\\n' "$*" >>"$NIX_CALLS"
"""


def _jobs() -> dict[str, tuple[str, dict[str, Any]]]:
    """Return every job of every workflow, by workflow/job name."""
    jobs = {}
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        definition = cast("dict[str, Any]", yaml.safe_load(workflow.read_text()))
        for name, job in definition["jobs"].items():
            jobs[f"{workflow.stem}/{name}"] = (yaml.safe_dump(job), job)
    return jobs


@spec(CAPABILITY, "Build and signing are isolated", "Check build job permissions")
def test_only_the_sign_job_sees_the_keys() -> None:
    jobs = _jobs()
    holders = {name for name, (text, _) in jobs.items() if any(s in text for s in SECRETS)}
    assert holders == {"build/sign"}
    environments = {name for name, (_, job) in jobs.items() if job.get("environment")}
    assert environments == {"build/sign"}
    assert jobs["build/sign"][1]["environment"] == ENVIRONMENT
    # No job that builds or tests reads a secret at all.
    for name in ("build/host-toolchain", "build/firmware", "build/system-test"):
        assert "secrets." not in jobs[name][0], name


@spec(CAPABILITY, "Build and signing are isolated", "Check what the signing job runs")
def test_the_sign_job_runs_only_the_signing_tools() -> None:
    steps = _jobs()["build/sign"][1]["steps"]
    actions = {step["uses"].split("@")[0] for step in steps if "uses" in step}
    assert actions <= SIGN_ACTIONS
    commands = [step["run"] for step in steps if "run" in step]
    assert len(commands) == 1
    assert "nix run .#sign-tools -- scripts/release-sign.sh" in commands[0]
    for builds in ("just", "make", "build.sh", "nix develop", "nix build"):
        assert builds not in commands[0], builds


@spec(CAPABILITY, "Signing targets", "Artifact does not match the manifest")
def test_a_changed_artifact_is_not_signed(
    build_output: Path, release_keys: Keys, tmp_path: Path
) -> None:
    changed = linked_copy(build_output, tmp_path / "build")
    replace(changed / INDEX, (changed / INDEX).read_bytes() + b"\0")
    with pytest.raises(subprocess.CalledProcessError) as failure:
        sign(changed, tmp_path / "signed", release_keys)
    assert "do not match manifest.json" in failure.value.stderr
    assert not (tmp_path / "signed").exists()


def _sign_job(tmp_path: Path, artifact: str, board: str) -> tuple[bool, list[str]]:
    """Run the sign job's script on an artifact whose manifest names ``board``.

    Return whether it succeeded and what it had nix run.
    """
    (step,) = [step for step in _jobs()["build/sign"][1]["steps"] if "run" in step]
    build = tmp_path / "unsigned" / f"firmware-unsigned-{artifact}"
    build.mkdir(parents=True)
    (build / MANIFEST_FILE).write_text(f'{{"board": "{board}"}}\n', encoding="utf-8")
    directory = tmp_path / "bin"
    directory.mkdir()
    (directory / "nix").write_text(NIX, encoding="utf-8")
    (directory / "nix").chmod(0o755)
    calls = tmp_path / "nix.calls"
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", step["run"]],
        cwd=REPO,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{directory}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_TEMP": str(tmp_path),
            "APK_KEY": "apk",
            "FW_KEY": "firmware",
            "NIX_CALLS": str(calls),
        },
    )
    made = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return result.returncode == 0, made


@spec(CAPABILITY, "Signing targets", "A build of another board")
@pytest.mark.parametrize(
    ("artifact", "named"),
    [
        pytest.param("..", BOARD, id="artifact of no board"),
        pytest.param(BOARD, f"../{BOARD}", id="manifest of another board"),
        pytest.param(BOARD, BOARD, id="the board's own"),
    ],
)
def test_each_build_is_signed_as_its_artifact_s_board(
    tmp_path: Path, artifact: str, named: str
) -> None:
    signed, made = _sign_job(tmp_path, artifact, named)
    # Only a board of boards/ whose manifest says so is signed, into its own
    # directory of the signed builds.
    if artifact == named:
        assert signed
        build = tmp_path / "unsigned" / f"firmware-unsigned-{BOARD}"
        (call,) = made
        assert call.startswith(
            f"run .#sign-tools -- scripts/release-sign.sh {build} {tmp_path}/signed/{BOARD} "
        )
    else:
        assert not signed
        assert made == []


@spec(CAPABILITY, "Signing targets", "Manifest that names a path outside the build")
@pytest.mark.parametrize("name", ["../outside/packages.adb", "targets/../../outside/packages.adb"])
def test_a_file_out_of_the_build_is_not_signed(
    build_output: Path, release_keys: Keys, tmp_path: Path, name: str
) -> None:
    # A package index beside the build, which the manifest names with its hash.
    outside = tmp_path / "outside" / "packages.adb"
    outside.parent.mkdir()
    shutil.copy(build_output / INDEX, outside)
    before = outside.read_bytes()
    build = linked_copy(build_output, tmp_path / "build")
    manifest = read_json(build / MANIFEST_FILE, Manifest)
    files = manifest.files | {name: sha256(outside)}
    write_json(build / MANIFEST_FILE, manifest.model_copy(update={"files": files}))
    with pytest.raises(subprocess.CalledProcessError) as failure:
        sign(build, tmp_path / "signed", release_keys)
    assert "lists a file that is no plain path inside its build" in failure.value.stderr
    assert not (tmp_path / "signed").exists()
    assert outside.read_bytes() == before


@spec(CAPABILITY, "Signing targets", "A file the manifest does not list")
def test_only_the_files_the_manifest_lists_are_signed(
    build_output: Path, release_keys: Keys, tmp_path: Path
) -> None:
    build = linked_copy(build_output, tmp_path / "build")
    (build / "targets" / "unlisted-factory.img.gz").write_bytes(b"unlisted")
    signed = sign(build, tmp_path / "signed", release_keys)
    listed = read_json(build_output / MANIFEST_FILE, Manifest).files
    held = {path.relative_to(signed).as_posix() for path in signed.rglob("*") if path.is_file()}
    assert held == listed.keys() | SIGNING


def _resigned(index: Path, path: Path, keys: Keys) -> Path:
    """Copy a package index to ``path``, signed with ``keys``' apk key alone."""
    shutil.copy(index, path)
    subprocess.run(
        ["apk", "--allow-untrusted", "--sign-key", keys.apk, "adbsign", "--reset-signatures", path],
        check=True,
        capture_output=True,
    )
    return path


def _verified(router: Router, index: Path) -> bool:
    """Return whether the router's apk takes ``index`` as signed by a key it trusts."""
    router.put(index, ON_ROUTER)
    return router.returncode(f"apk verify {ON_ROUTER}") == 0


@spec(CAPABILITY, "Signing targets", "Signed package index")
def test_the_router_reads_the_signed_index(router: Router, signed_repo: Path) -> None:
    # The router trusts the session's release keys alone (conftest).
    assert _verified(router, signed_repo / INDEX)
    listed = router.run(f"apk --repositories-file /dev/null --repository {ON_ROUTER} search kmod-")
    assert "kmod-" in listed


@spec(CAPABILITY, "Devices trust only release keys", "Check trust anchors in the image")
def test_the_image_trusts_only_the_release_keys(
    emulation_dir: Path, emulation_source: EmulationSource, tmp_path: Path
) -> None:
    if emulation_source.build.name != "ci":
        pytest.skip("only the release build (ci profile) carries the release keys (design D1)")
    root = extract_root(emulation_dir / "disk.raw", tmp_path / "root")
    for anchors in (APK_KEYS, FIRMWARE_KEYS):
        present = sorted(key.name for key in (root / anchors).iterdir())
        released = sorted(key.name for key in (KEYRING / anchors).glob("*"))
        assert present == released, anchors


@spec(CAPABILITY, "Devices trust only release keys", "Index signed with another key")
def test_an_index_of_another_key_is_refused(
    router: Router, signed_repo: Path, tmp_path: Path
) -> None:
    other = Keys.make(tmp_path / "other", "other")
    assert not _verified(router, _resigned(signed_repo / INDEX, tmp_path / "other.adb", other))
    refused = router.run(
        f"apk --repositories-file /dev/null --repository {ON_ROUTER} search kmod- 2>&1 || true"
    )
    assert "UNTRUSTED" in refused


@spec(CAPABILITY, "Key rotation support", "Rotation transition period")
def test_old_and_new_keys_during_a_rotation(
    router: Router, signed_repo: Path, release_keys: Keys, tmp_path: Path
) -> None:
    # The image holds the old key (the session's) and the new one.
    new = Keys.make(tmp_path / "new", "new")
    for key in (new.keyring / APK_KEYS).iterdir():
        router.put(key, f"/{APK_KEYS}/{key.name}")
    assert _verified(router, signed_repo / INDEX)
    assert _verified(router, _resigned(signed_repo / INDEX, tmp_path / "new.adb", new))
    del release_keys  # the old key, trusted since boot
