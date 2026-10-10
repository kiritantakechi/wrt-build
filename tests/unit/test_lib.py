"""The shell library's modules (scripts/lib/): the tree, the caches, the toolchain and seeds."""

import hashlib
import os
import re
from pathlib import Path

import pytest

from wrt_tests.model.boards import load_all
from wrt_tests.model.shell import awk_program, library

REPO = Path(__file__).resolve().parents[2]
PROFILES = [
    line.split(":")[0]
    for line in (REPO / "config" / "profiles").read_text().splitlines()
    if line and not line.startswith("#")
]


def _missing_lines(tmp_path: Path, wanted: str, actual: str) -> list[str]:
    """Return what missing_config_lines finds of ``wanted`` missing from ``actual``."""
    (tmp_path / "wanted").write_text(wanted)
    (tmp_path / "actual").write_text(actual)
    result = library("tree", 'missing_config_lines "$1" "$2"', "wanted", "actual", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
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
    result = library("cache", 'compiler_cache_trim "$1" "$2"', str(tree), str(start))
    assert result.returncode == 0, result.stderr
    kept = {str(path.relative_to(tree)) for path in tree.rglob("*") if path.is_file()}
    assert kept == {".config", "tmp/go-build/aa/used", "tmp/go-build/bb/new", ".sccache/a/used"}


def _rust_std(tree: Path) -> str:
    """Return what toolchain_rust_std makes of the Rust libraries in ``tree``."""
    result = library("toolchain", 'toolchain_rust_std "$1"', str(tree))
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


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
    result = library("toolchain", 'toolchain_stages "$1"', str(log))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "package/feeds/packages/golang1.27 [compile]",
        "package/feeds/packages/rust [compile]",
        "toolchain/gcc/final [compile]",
        "tools/flock [prepare]",
    ]


def _tree(command: str, *args: str) -> None:
    """Run ``command`` with the tree module loaded; its arguments are ``args``."""
    result = library("tree", command, *args)
    assert result.returncode == 0, result.stderr


OLD = 1_700_000_000


def test_an_unchanged_link_keeps_its_time(tmp_path: Path) -> None:
    link = tmp_path / "link"
    _tree('symlink "$1" "$2"', "target", str(link))
    os.utime(link, (OLD, OLD), follow_symlinks=False)
    _tree('symlink "$1" "$2"', "target", str(link))
    assert link.lstat().st_mtime == OLD
    _tree('symlink "$1" "$2"', "other", str(link))
    assert link.readlink() == Path("other")


def test_an_unchanged_file_keeps_its_time(tmp_path: Path) -> None:
    file = tmp_path / "file"
    file.write_text("same\n")
    os.utime(file, (OLD, OLD))
    _tree('printf "same\\n" | update_file "$1"', str(file))
    assert file.stat().st_mtime == OLD
    _tree('printf "other\\n" | update_file "$1"', str(file))
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
        _tree('configure_tree "$1" "$2"', str(tree), str(seed))
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


def test_go_cache_counts_what_go_compiled(tmp_path: Path) -> None:
    # Go writes an action entry, its creation time inside, only for an action it
    # ran; a hit refreshes an old entry's file time alone.
    start = 1_700_000_000
    tree = tmp_path / "openwrt"
    cache = tree / "tmp" / "go-build"
    entries = (
        ("aa", "11", 10, start - 86_400, b"compiled"),  # a hit
        ("bb", "22", 10, start + 60, b"compiled"),  # compiled anew
        ("cc", "e3", 0, start + 60, None),  # an action with no output
        ("dd", "44", 514, start + 60, b"go index v2 ..."),  # sources unpacked anew
    )
    for action, output, size, created, data in entries:
        action_id, output_id = action * 32, output * 32
        entry = cache / action / f"{action_id}-a"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(f"v1 {action_id} {output_id} {size:20d} {created * 10**9:20d}\n")
        if data is not None:
            (cache / output).mkdir(exist_ok=True)
            (cache / output / f"{output_id}-d").write_bytes(data)
    for path in cache.rglob("*-[ad]"):
        os.utime(path, (start + 120, start + 120))
    result = library("cache", 'go_cache_compiled "$1" "$2"', str(tree), str(start))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1"


def _compose(profile: str, board: str, tmp_path: Path) -> str:
    """Return the seed compose_seeds composes for ``profile`` and ``board`` (none: "").

    The tree is ``tmp_path``'s openwrt.
    """
    tree = tmp_path / "openwrt"
    tree.mkdir(exist_ok=True)
    output = tmp_path / f"{profile}-{board or 'neutral'}.config"
    result = library("seeds", 'compose_seeds "$@"', str(tree), profile, board, str(output))
    assert result.returncode == 0, result.stderr
    return output.read_text()


def _options(seed: str) -> list[str]:
    """Return the option each line of ``seed`` sets, in order."""
    return [
        match.group(1) or match.group(2)
        for line in seed.splitlines()
        if (match := re.fullmatch(r"(CONFIG_[^= ]+)=.*|# (CONFIG_[^ ]+) is not set", line))
    ]


def test_a_later_seed_replaces_an_earlier_line(tmp_path: Path) -> None:
    # The later seed's line stands where it stands; comments stay.
    (tmp_path / "a.seed").write_text(
        '# a\nCONFIG_A=y\n# CONFIG_B is not set\nCONFIG_C="-O2"\nCONFIG_D=m\n'
    )
    (tmp_path / "b.seed").write_text('# b\nCONFIG_B=y\nCONFIG_C="-O3"\n')
    result = awk_program("merge-seeds.awk", "a.seed", "b.seed", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == '# a\nCONFIG_A=y\nCONFIG_D=m\n# b\nCONFIG_B=y\nCONFIG_C="-O3"\n'


@pytest.mark.parametrize("profile", PROFILES)
def test_a_composed_seed_holds_one_line_per_option(profile: str, tmp_path: Path) -> None:
    # configure_tree checks every line of it against the configuration, which can
    # hold only one value per option.
    for board in ("", *(board.id for board in load_all())):
        options = _options(_compose(profile, board, tmp_path))
        assert len(options) == len(set(options)), (profile, board)


def test_board_only_seeds_leave_the_toolchain_alone(tmp_path: Path) -> None:
    # The toolchain is built from the board-neutral composition, which its key
    # hashes: the ubsan profile's is the dev profile's, so is its toolchain.
    assert _compose("ubsan", "", tmp_path) == _compose("dev", "", tmp_path)


def test_board_only_seeds_build_apart(tmp_path: Path) -> None:
    # The ubsan seed's flags replace the toolchain seed's, the board's -mcpu still
    # comes last, and the build has directories of its own.
    seed = _compose("ubsan", "r4s", tmp_path).splitlines()
    ubsan = (REPO / "config" / "ubsan.seed").read_text().splitlines()
    assert [line for line in seed if line.startswith("CONFIG_TARGET_OPTIMIZATION=")] == [
        line for line in ubsan if line.startswith("CONFIG_TARGET_OPTIMIZATION=")
    ]
    assert 'CONFIG_EXTRA_OPTIMIZATION="-fno-caller-saves -fno-plt -O3 -mcpu=' in "\n".join(seed)
    assert 'CONFIG_BUILD_SUFFIX="r4s_ubsan"' in seed
    assert f'CONFIG_BINARY_FOLDER="{tmp_path / "openwrt"}/bin/r4s_ubsan"' in seed
    assert 'CONFIG_BUILD_SUFFIX="r4s"' in _compose("dev", "r4s", tmp_path).splitlines()


def test_the_ubsan_seed_extends_the_toolchain_seed() -> None:
    # It replaces the option's value whole: what the toolchain seed holds, then UBSan.
    def value(seed: str) -> str:
        text = (REPO / "config" / f"{seed}.seed").read_text()
        found = re.search(r'^CONFIG_TARGET_OPTIMIZATION="(.*)"$', text, re.MULTILINE)
        assert found
        return str(found[1])

    assert value("ubsan") == f"{value('toolchain')} -fsanitize=undefined -fsanitize-trap=undefined"
