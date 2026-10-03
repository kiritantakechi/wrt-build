"""The helpers of scripts/lib.sh: the configuration's guard and the cache trim."""

import os
import subprocess
from pathlib import Path

LIB = Path(__file__).resolve().parents[2] / "scripts" / "lib.sh"


def _missing_lines(tmp_path: Path, wanted: str, actual: str) -> list[str]:
    """Return what missing_config_lines finds of ``wanted`` missing from ``actual``."""
    (tmp_path / "wanted").write_text(wanted)
    (tmp_path / "actual").write_text(actual)
    result = subprocess.run(
        ["sh", "-c", f'. "{LIB}" && missing_config_lines "$1" "$2"', "sh", "wanted", "actual"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines()]


def test_every_seed_line_is_checked(tmp_path: Path) -> None:
    # Packages' symbols hold "-", "." and "+": each such line the configuration
    # lacks, or holds with another value, is named like any other.
    wanted = """\
# The seed's comments are no options.
CONFIG_TARGET_rockchip=y
# CONFIG_PACKAGE_openwrt-keyring is not set
CONFIG_PACKAGE_kmod-nf-conntrack6=m
CONFIG_PACKAGE_libstdcpp6.x+=y
CONFIG_PACKAGE_wrt-keyring=y
"""
    actual = """\
CONFIG_TARGET_rockchip=y
CONFIG_PACKAGE_openwrt-keyring=y
CONFIG_PACKAGE_wrt-keyring=y
"""
    assert _missing_lines(tmp_path, wanted, actual) == [
        "# CONFIG_PACKAGE_openwrt-keyring is not set",
        "CONFIG_PACKAGE_kmod-nf-conntrack6=m",
        "CONFIG_PACKAGE_libstdcpp6.x+=y",
    ]


def test_trim_keeps_what_the_build_used(tmp_path: Path) -> None:
    # Go's and sccache's caches refresh an entry's time when they use it: what a
    # build begun at `start` did not use is older than `start`.
    start = 1_700_000_000
    cache = tmp_path / "cache"
    for name, mtime in (("aa/used", start + 60), ("aa/unused", start - 3600), ("bb/new", start)):
        entry = cache / name
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(name)
        os.utime(entry, (mtime, mtime))
    subprocess.run(
        ["sh", "-c", f'. "{LIB}" && trim_unused "$1" "$2"', "sh", str(cache), str(start)],
        check=True,
    )
    assert sorted(str(path.relative_to(cache)) for path in cache.rglob("*") if path.is_file()) == [
        "aa/used",
        "bb/new",
    ]
