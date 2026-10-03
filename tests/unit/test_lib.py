"""The helpers of scripts/lib.sh: the tree's files, the caches and the toolchain."""

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


def test_toolchain_stages_name_what_only_toolchain_build_builds(tmp_path: Path) -> None:
    # A board's time log: what tools/, toolchain/ or the Go and Rust host
    # toolchains ran is named once per stage; the board's own packages are not.
    log = tmp_path / "build-time-r4s.tsv"
    log.write_text(
        "".join(
            f"{time}\t{event}\t{stage}\t{name}\n"
            for time, event, stage, name in (
                (1, "begin", "prepare", "tools/flock"),
                (2, "end", "prepare", "tools/flock"),
                (3, "begin", "compile", "toolchain/gcc/final"),
                (4, "begin", "compile", "package/feeds/packages/golang1.27"),
                (5, "begin", "compile", "package/feeds/packages/rust"),
                (6, "begin", "compile", "package/feeds/packages/rust"),
                (7, "begin", "compile", "package/feeds/packages/dae"),
                (8, "begin", "compile", "package/feeds/packages/golang-protobuf"),
                (9, "begin", "compile", "package/feeds/wrt/einat"),
                (10, "begin", "compile", "target/linux"),
            )
        )
    )
    result = subprocess.run(
        ["sh", "-c", f'. "{LIB}" && toolchain_stages "$1"', "sh", str(log)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == [
        "package/feeds/packages/golang1.27 [compile]",
        "package/feeds/packages/rust [compile]",
        "toolchain/gcc/final [compile]",
        "tools/flock [prepare]",
    ]


def _lib(script: str, *args: str) -> None:
    """Run ``script`` with scripts/lib.sh sourced; its arguments are ``args``."""
    subprocess.run(["sh", "-c", f'. "{LIB}" && {script}', "sh", *args], check=True)


OLD = 1_700_000_000


def test_an_unchanged_link_keeps_its_time(tmp_path: Path) -> None:
    link = tmp_path / "link"
    _lib('symlink "$1" "$2"', "target", str(link))
    os.utime(link, (OLD, OLD), follow_symlinks=False)
    _lib('symlink "$1" "$2"', "target", str(link))
    assert link.lstat().st_mtime == OLD
    _lib('symlink "$1" "$2"', "other", str(link))
    assert link.readlink() == Path("other")


def test_an_unchanged_file_keeps_its_time(tmp_path: Path) -> None:
    file = tmp_path / "file"
    file.write_text("same\n")
    os.utime(file, (OLD, OLD))
    _lib('printf "same\\n" | update_file "$1"', str(file))
    assert file.stat().st_mtime == OLD
    _lib('printf "other\\n" | update_file "$1"', str(file))
    assert file.read_text() == "other\n"
    assert file.stat().st_mtime > OLD
    assert sorted(path.name for path in tmp_path.iterdir()) == ["file"]


def test_an_unchanged_configuration_keeps_its_time(tmp_path: Path) -> None:
    # A stand-in tree whose defconfig keeps the seed as the configuration.
    tree = tmp_path / "openwrt"
    (tree / "tmp").mkdir(parents=True)
    (tree / "Makefile").write_text("defconfig:\n\t@:\n")
    config = tree / ".config"
    seed = tmp_path / "seed"

    def configure(text: str) -> float:
        seed.write_text(text)
        _lib('TREE="$1" && configure_tree "$2"', str(tree), str(seed))
        return config.stat().st_mtime

    board = 'CONFIG_BUILD_SUFFIX="r4s"\nCONFIG_X=y\n'
    configure(board)
    # The build directories were configured with it long ago.
    for path in (config, tree / "tmp" / "wrt-config-r4s"):
        os.utime(path, (OLD, OLD))
    assert configure("CONFIG_X=y\n") > OLD
    assert configure(board) == OLD
    assert configure(board.replace("=y", "=n")) > OLD
    assert configure(board) > OLD
