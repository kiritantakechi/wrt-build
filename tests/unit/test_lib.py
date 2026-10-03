"""The helpers of scripts/lib.sh: the configuration's guard, the cache trim and the record."""

import hashlib
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
    # The caches refresh an entry's time when they use it: sccache on every hit,
    # Go only an entry more than an hour old. What a build begun at `start` used
    # is newer than `start` in sccache's cache, and than the hour before it in Go's.
    start = 1_700_000_000
    tree = tmp_path / "openwrt"
    entries = {
        "tmp/go-build/aa/used": start - 1800,
        "tmp/go-build/aa/unused": start - 3600,
        "tmp/go-build/bb/new": start + 60,
        ".sccache/a/used": start + 60,
        ".sccache/a/unused": start,
    }
    for name, mtime in entries.items():
        entry = tree / name
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(name)
        os.utime(entry, (mtime, mtime))
    (tree / ".config").touch()
    subprocess.run(
        [
            "sh",
            "-c",
            f'TREE="$1" && . "{LIB}" && compiler_cache_trim "$2"',
            "sh",
            str(tree),
            str(start),
        ],
        check=True,
    )
    kept = {str(path.relative_to(tree)) for path in tree.rglob("*") if path.is_file()}
    assert kept == {".config", "tmp/go-build/aa/used", "tmp/go-build/bb/new", ".sccache/a/used"}


def _rust_std(tree: Path) -> str:
    """Return what toolchain_rust_std makes of the Rust libraries in ``tree``."""
    return subprocess.run(
        ["sh", "-c", f'TREE="$1" && . "{LIB}" && toolchain_rust_std', "sh", str(tree)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_an_uninstalled_rust_has_no_standard_library(tmp_path: Path) -> None:
    # Rust's uninstaller removes the libraries and leaves their directories.
    target = "aarch64-unknown-linux-musl"
    lib = tmp_path / "staging_dir" / "hostpkg" / "lib" / "rustlib" / target / "lib"
    lib.mkdir(parents=True)
    assert _rust_std(tmp_path) == ""
    (lib / "libstd.rlib").write_bytes(b"std")
    listing = f"{hashlib.sha256(b'std').hexdigest()}  ./{target}/lib/libstd.rlib\n"
    assert _rust_std(tmp_path) == hashlib.sha256(listing.encode()).hexdigest()
