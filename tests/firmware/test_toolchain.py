"""firmware/toolchain: optimisation comes from configuration, not from build system patches."""

from pathlib import Path

from wrt_tests import spec

CAPABILITY = "firmware/toolchain"
PATCHES = Path(__file__).resolve().parents[2] / "patches" / "openwrt"


@spec(CAPABILITY, "只靠配置实现优化，不改构建系统", "审计补丁队列")
def test_patch_queue_leaves_target_mk_alone() -> None:
    changed = {
        line.split()[3].removeprefix("b/")
        for patch in PATCHES.glob("*.patch")
        for line in patch.read_text().splitlines()
        if line.startswith("diff --git ")
    }
    assert changed
    assert "include/target.mk" not in changed
