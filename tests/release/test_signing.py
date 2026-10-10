"""release/signing: a job of its own signs with keys only it sees; devices trust only them.

The workflow checks read .github/workflows. Signing runs scripts/release-sign.sh,
the script the sign job runs, with the session's release keys; the router
trusts those keys (conftest), as a release image trusts the production ones.
"""

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml

from wrt_tests import spec
from wrt_tests.model.keys import APK_KEYS, FIRMWARE_KEYS, Keys, sign
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
# The only actions the sign job may use: the checkout, Nix and the artifacts.
SIGN_ACTIONS = {"actions/checkout", "DeterminateSystems/nix-installer-action"} | {
    f"actions/{verb}-artifact" for verb in ("download", "upload")
}


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
