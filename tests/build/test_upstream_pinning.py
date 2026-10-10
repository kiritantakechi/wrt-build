"""build/upstream-pinning: every patch states its upstream status, with write-ups in step."""

from wrt_tests import spec
from wrt_tests.model.patches import (
    DOC,
    repository_patches,
    unstated,
    without_patch,
    without_write_up,
    write_ups,
)

CAPABILITY = "build/upstream-pinning"
REQUIREMENT = "Every patch states its upstream status"


@spec(CAPABILITY, REQUIREMENT, "Patch without a status")
def test_every_patch_states_its_status() -> None:
    patches = repository_patches()
    assert patches
    assert unstated(patches) == []


@spec(CAPABILITY, REQUIREMENT, "Patch meant for upstream without a write-up")
def test_patches_meant_for_upstream_have_their_write_ups() -> None:
    assert without_write_up(repository_patches(), write_ups(DOC.read_text())) == []


@spec(CAPABILITY, REQUIREMENT, "Write-up without a patch")
def test_every_write_up_names_its_patch() -> None:
    assert without_patch(repository_patches(), write_ups(DOC.read_text())) == []
