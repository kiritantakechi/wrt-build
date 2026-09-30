"""build/boards: every board is described once, and built on its own from one tree."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from wrt_tests import spec
from wrt_tests.boards import BOARDS_DIR, Board, load_all
from wrt_tests.emu import MANIFEST_FILE, sha256

CAPABILITY = "build/boards"
REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "build.yml"
# What the board facts must stay out of, and the places they belong instead:
# the descriptions and each board's own U-Boot fragments.
SEARCHED = ("scripts", "config", "feed", "files", "patches", "tests", "uboot", ".github")
SEARCHED_FILES = ("justfile", "flake.nix")
BOARD_CHECK = Path(sys.executable).with_name("board-check")
BOARD_RECIPES = ("build", "config", "test", "drill-base")
IMAGES = ("*-factory.img.gz", "*-sysupgrade.tar.gz")
# The board-neutral flags a toolchain records (config/toolchain.seed after the target's).
NEUTRAL_CFLAGS = "-Os -pipe -mcpu=generic -fno-caller-saves -fno-plt -O2 -fhonour-copts"
LIBC = b"the toolchain's C library"
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "upstream",
    "GIT_AUTHOR_EMAIL": "upstream@example.net",
    "GIT_COMMITTER_NAME": "upstream",
    "GIT_COMMITTER_EMAIL": "upstream@example.net",
}
PATCHES = REPO / "patches" / "openwrt"
# Buildbot mode's version check in toolchain/Makefile: the rule and its recipe.
VERSION_CHECK = re.compile(
    r"^  \$\(TOOLCHAIN_DIR\)/stamp/\.ver_check:.*\n(?:\t.*\n)+", re.MULTILINE
)
# Makes started a millisecond apart check at once, as world's sub-makes do; the
# unpatched check deletes the toolchain in most rounds.
MAKES = 8
ROUNDS = 20


def _builds_beside(build_output: Path) -> list[tuple[Board, Path]]:
    """Return every board's build of the same profile in the work directory of ``build_output``."""
    out, profile = build_output.parents[1], build_output.name
    return [
        (board, out / board.id / profile)
        for board in load_all()
        if (out / board.id / profile / MANIFEST_FILE).is_file()
    ]


def _manifest(build: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads((build / MANIFEST_FILE).read_text()))


@spec(CAPABILITY, "One description per board", "A malformed description")
def test_a_malformed_description_is_named(tmp_path: Path) -> None:
    boards = tmp_path / "boards"
    shutil.copytree(BOARDS_DIR, boards)
    description = json.loads((boards / "r6s.json").read_text())
    del description["cpu"]
    description["emulator"]["cores"] = "eight"
    (boards / "r6s.json").write_text(json.dumps(description))
    result = subprocess.run(
        [BOARD_CHECK, "--boards", boards], capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "r6s.json: cpu: Field required" in result.stderr
    assert "r6s.json: emulator.cores:" in result.stderr
    assert "r4s.json" not in result.stderr


@spec(CAPABILITY, "One description per board", "No board named outside its description")
def test_no_board_is_named_outside_its_description() -> None:
    boards = load_all()
    facts = {
        fact.lower()
        for board in boards
        for fact in (
            board.device,
            board.board_name,
            board.soc.compatible,
            board.soc.compatible.split(",")[-1],
        )
    }
    fragments = {f"uboot/board-{board.id}.{kind}" for board in boards for kind in ("env", "config")}
    listed = subprocess.run(
        [
            *("git", "-C", REPO, "ls-files", "--cached", "--others", "--exclude-standard"),
            *("--", *SEARCHED, *SEARCHED_FILES),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    naming = {}
    for name in sorted(set(listed) - fragments):
        path = REPO / name
        if not path.is_file():
            continue
        text = path.read_bytes().decode(errors="replace").lower()
        if found := sorted(fact for fact in facts if fact in text):
            naming[name] = found
    assert naming == {}


@spec(CAPABILITY, "Supported boards", "Every board goes through the pipeline")
def test_every_board_goes_through_the_pipeline() -> None:
    listed = subprocess.run(
        ["just", "--justfile", REPO / "justfile", "boards"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert json.loads(listed) == [board.id for board in load_all()]
    jobs = cast("dict[str, Any]", yaml.safe_load(WORKFLOW.read_text()))["jobs"]
    # host-toolchain lists the boards, as just boards prints them...
    host = jobs["host-toolchain"]
    (step,) = [step for step in host["steps"] if step.get("id") == "boards"]
    assert "just boards" in step["run"]
    assert host["outputs"]["boards"] == "${{ steps.boards.outputs.boards }}"
    # ...and each board is built, tested and drilled on its own.
    for name in ("firmware", "system-test", "drill"):
        board = jobs[name]["strategy"]["matrix"]["board"]
        assert board == "${{ fromJSON(needs.host-toolchain.outputs.boards) }}", name

    def downloads(job: str) -> list[dict[str, str]]:
        return [
            step["with"]
            for step in jobs[job]["steps"]
            if step.get("uses", "").startswith("actions/download-artifact@")
        ]

    # One sign job takes every board's build, and publish every signed one,
    # once every board's drill passed.
    (upload,) = [
        step for step in jobs["firmware"]["steps"] if step.get("name") == "Upload unsigned firmware"
    ]
    assert upload["with"]["name"] == "firmware-unsigned-${{ matrix.board }}"
    assert downloads("sign") == [
        {"pattern": "firmware-unsigned-*", "path": "${{ runner.temp }}/unsigned"}
    ]
    assert [download["name"] for download in downloads("publish")] == ["firmware-signed"]
    assert "drill" in jobs["publish"]["needs"]


@spec(CAPABILITY, "One build per board from one tree", "Build an unknown board")
@pytest.mark.parametrize("recipe", BOARD_RECIPES)
def test_an_unknown_board_is_refused(recipe: str, tmp_path: Path) -> None:
    result = subprocess.run(
        ["just", "--justfile", REPO / "justfile", recipe, "nope"],
        env={**os.environ, "WRT_WORKDIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    known = " ".join(board.id for board in load_all())
    assert result.returncode != 0
    assert f"no board 'nope' (boards: {known})" in result.stderr
    assert list(tmp_path.iterdir()) == []


@spec(CAPABILITY, "One build per board from one tree", "Two boards in one tree")
def test_boards_build_apart(build_output: Path) -> None:
    builds = _builds_beside(build_output)
    if all(build == build_output for _, build in builds):
        pytest.skip("no other board's build beside this one")
    tree = Path(os.environ["WRT_WORKDIR"]) / "openwrt"
    variants = {board.uboot.variant for board, _ in builds}
    for board, build in builds:
        manifest = _manifest(build)
        assert manifest["board"] == board.id
        # Its own build and staging directories, and its own output directory...
        config = (build / "diffconfig").read_text().splitlines()
        assert f'CONFIG_BUILD_SUFFIX="{board.id}"' in config
        assert any(
            line.startswith("CONFIG_BINARY_FOLDER=") and line.endswith(f'/bin/{board.id}"')
            for line in config
        )
        # ...which hold its build objects alone: its own U-Boot, no other board's...
        (build_dir,) = (tree / "build_dir").glob(f"target-*_{board.id}")
        built = {variant for variant in variants if (build_dir / f"u-boot-{variant}").is_dir()}
        assert built == {board.uboot.variant}
        # ...and its own images alone, still the ones of its manifest while the
        # tree's last build of the board was of this profile.
        (targets,) = (tree / "bin" / board.id / "targets").glob("*/*")
        images = {path.name for pattern in IMAGES for path in targets.glob(pattern)}
        assert len(images) == len(IMAGES)
        assert all(f"-{board.device}-" in name for name in images), images
        if (targets / "config.buildinfo").read_text() == (build / "diffconfig").read_text():
            assert {name: sha256(targets / name) for name in images} == {
                name: manifest["files"][f"targets/{name}"] for name in images
            }


@spec(CAPABILITY, "One toolchain for every board", "Toolchain free of board flags")
def test_the_toolchain_carries_no_board_flags(build_output: Path) -> None:
    builds = _builds_beside(build_output)
    toolchains = {_manifest(build)["toolchain_cflags"] for _, build in builds}
    assert len(toolchains) == 1, toolchains
    flags = set(toolchains.pop().split())
    assert "-mcpu=generic" in flags
    assert not {f"-mcpu={board.cpu}" for board in load_all()} & flags


def _tree_with_toolchain(workdir: Path, board: Board, record: dict[str, str] | None) -> Path:
    """Write a stand-in tree configured for ``board`` whose toolchain has ``record``.

    Its Makefile answers build.sh's val.* queries and marks any build it is asked for.
    """
    tree = workdir / "openwrt"
    toolchain = tree / "staging_dir" / "toolchain"
    (toolchain / "lib").mkdir(parents=True)
    (toolchain / "lib" / "libc.so").write_bytes(LIBC)
    if record is not None:
        (toolchain / "wrt-toolchain.json").write_text(json.dumps(record))
    (tree / ".config").write_text(f'CONFIG_BUILD_SUFFIX="{board.id}"\n')
    (tree / "Makefile").write_text(
        f"TOOLCHAIN_DIR := {toolchain}\n"
        ".DEFAULT_GOAL := world\n"
        "val.%:\n\t@echo '$($*)'\n"
        "download world:\n\t@touch $(CURDIR)/built\n"
    )
    return tree


def _board_toolchains() -> list[tuple[str, dict[str, str] | None, str | None]]:
    libc = hashlib.sha256(LIBC).hexdigest()
    return [
        ("neutral", {"cflags": NEUTRAL_CFLAGS, "libc": libc}, None),
        ("no-record", None, "has no record of its flags"),
        *(
            (
                f"{board.id}-mcpu",
                {"cflags": f"{NEUTRAL_CFLAGS} -mcpu={board.cpu}", "libc": libc},
                f"built with {board.id}'s -mcpu={board.cpu}",
            )
            for board in load_all()
        ),
        (
            "other-libc",
            {"cflags": NEUTRAL_CFLAGS, "libc": "0" * 64},
            "C library is not the one its record names",
        ),
    ]


def _commit_toolchain(tree: Path) -> None:
    """Make ``tree`` a repository whose one commit holds ``toolchain/``."""
    (tree / "toolchain").mkdir(parents=True)
    (tree / "toolchain" / "Makefile").touch()
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    subprocess.run(["git", "add", "toolchain"], cwd=tree, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "toolchain"],
        cwd=tree,
        check=True,
        env={**os.environ, **GIT_IDENTITY},
    )


def _toolchain_version(tree: Path) -> str:
    """Return the version buildbot mode stamps a toolchain with: the last commit of toolchain/."""
    return subprocess.run(
        ["git", "log", "--format=%h", "-1", "toolchain"],
        cwd=tree,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _version_check() -> str:
    """Return buildbot mode's version check as the patch series leaves toolchain/Makefile."""
    for patch in sorted(PATCHES.glob("*.patch")):
        for diff in patch.read_text().split("\ndiff --git ")[1:]:
            if not diff.startswith("a/toolchain/Makefile "):
                continue
            # The patched side of each hunk: its context and its added lines.
            patched = "".join(
                f"{line[1:]}\n"
                for line in diff.splitlines()
                if line.startswith((" ", "+")) and not line.startswith("+++")
            )
            if rule := VERSION_CHECK.search(patched):
                return rule.group()
    pytest.fail("no patch in patches/openwrt carries the version check of toolchain/Makefile")


def _tree_to_build_toolchain(workdir: Path, libc: bytes | None, record: bytes | None) -> Path:
    """Write a stand-in tree whose toolchain holds ``libc``, recorded as ``record``'s.

    Its Makefile answers toolchain-build.sh's val.* queries and builds a toolchain,
    with LIBC for its C library, only where there is none, as make does; it
    marks the tree when it does.
    """
    tree = workdir / "openwrt"
    toolchain = tree / "staging_dir" / "toolchain"
    _commit_toolchain(tree)
    (tree / "feeds.conf").touch()
    neutral = workdir / "neutral-libc.so"
    neutral.write_bytes(LIBC)
    if libc is not None:
        (toolchain / "lib").mkdir(parents=True)
        (toolchain / "lib" / "libc.so").write_bytes(libc)
    if record is not None:
        toolchain.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(record).hexdigest()
        (toolchain / "wrt-toolchain.json").write_text(
            json.dumps({"cflags": NEUTRAL_CFLAGS, "libc": digest})
        )
    (tree / "Makefile").write_text(
        f"TOOLCHAIN_DIR := {toolchain}\n"
        f"TARGET_CFLAGS := {NEUTRAL_CFLAGS}\n"
        "val.%:\n\t@echo '$($*)'\n"
        "defconfig tools/install:\n\t@:\n"
        "toolchain/install:\n"
        "\t@[ -f $(TOOLCHAIN_DIR)/lib/libc.so ] || { mkdir -p $(TOOLCHAIN_DIR)/lib"
        f" && cp {neutral} $(TOOLCHAIN_DIR)/lib/libc.so && touch $(CURDIR)/built; }}\n"
        "$(TOOLCHAIN_DIR)/stamp/.toolchain_compile:\n\t@mkdir -p $(@D) && touch $@\n"
    )
    return tree


def _toolchain_build(tree: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [REPO / "scripts" / "toolchain-build.sh"],
        env={**os.environ, "WRT_WORKDIR": str(tree.parent)},
        capture_output=True,
        text=True,
        check=False,
    )


@spec(CAPABILITY, "One toolchain for every board", "Rebuild a changed toolchain")
@pytest.mark.parametrize(
    ("libc", "rebuilt"),
    [(LIBC, False), (b"a C library built with a board's -mcpu", True), (None, True)],
    ids=["as recorded", "changed", "none"],
)
def test_a_changed_toolchain_is_built_anew(
    libc: bytes | None, tmp_path: Path, *, rebuilt: bool
) -> None:
    tree = _tree_to_build_toolchain(tmp_path, libc, LIBC)
    result = _toolchain_build(tree)
    assert result.returncode == 0, result.stderr
    assert (tree / "built").exists() == rebuilt, result.stderr
    toolchain = tree / "staging_dir" / "toolchain"
    assert (toolchain / "lib" / "libc.so").read_bytes() == LIBC
    record = json.loads((toolchain / "wrt-toolchain.json").read_text())
    assert record == {"cflags": NEUTRAL_CFLAGS, "libc": hashlib.sha256(LIBC).hexdigest()}


@spec(CAPABILITY, "One toolchain for every board", "Keep the toolchain in buildbot mode")
def test_the_toolchain_names_its_version(tmp_path: Path) -> None:
    tree = _tree_to_build_toolchain(tmp_path, LIBC, LIBC)
    result = _toolchain_build(tree)
    assert result.returncode == 0, result.stderr
    # Buildbot mode deletes a toolchain whose version stamp does not name the
    # last commit of toolchain/ (toolchain/Makefile).
    stamp = tree / "staging_dir" / "toolchain" / "stamp" / ".ver_check"
    assert stamp.read_text() == _toolchain_version(tree)


def _stamped_toolchain(tree: Path, version: str) -> tuple[Path, Path]:
    """Put a toolchain stamped with ``version`` into ``tree``; return its compiler and stamp.

    The stamp is older than tmp/.build, as a stamp that names the current version
    stays after every make from the top level, which touches tmp/.build.
    """
    toolchain = tree / "staging_dir" / "toolchain"
    shutil.rmtree(toolchain, ignore_errors=True)
    compiler = toolchain / "bin" / "gcc"
    stamp = toolchain / "stamp" / ".ver_check"
    compiler.parent.mkdir(parents=True)
    compiler.touch()
    stamp.parent.mkdir()
    stamp.write_text(version)
    os.utime(stamp, (0, 0))
    (tree / "tmp").mkdir(exist_ok=True)
    (tree / "tmp" / ".build").touch()
    return compiler, stamp


@spec(CAPABILITY, "One toolchain for every board", "Check the version from parallel makes")
def test_parallel_makes_check_the_version(tmp_path: Path) -> None:
    tree = tmp_path / "openwrt"
    _commit_toolchain(tree)
    version = _toolchain_version(tree)
    (tree / "Makefile").write_text(
        f"TOPDIR := {tree}\n"
        "TMP_DIR := $(TOPDIR)/tmp\n"
        "BUILD_DIR := $(TOPDIR)/build_dir/target\n"
        "STAGING_DIR := $(TOPDIR)/staging_dir/target\n"
        "TOOLCHAIN_DIR := $(TOPDIR)/staging_dir/toolchain\n"
        "BUILD_DIR_TOOLCHAIN := $(TOPDIR)/build_dir/toolchain\n" + _version_check()
    )
    for _ in range(ROUNDS):
        compiler, stamp = _stamped_toolchain(tree, version)
        makes = []
        for _ in range(MAKES):
            makes.append(
                subprocess.Popen(
                    ["make", "-s", "-C", tree, stamp],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
            time.sleep(0.001)
        for make in makes:
            _, errors = make.communicate()
            assert make.returncode == 0, errors
        assert compiler.exists()
        assert stamp.read_text() == version
    # A toolchain of another version is still deleted, and stamped anew.
    compiler, stamp = _stamped_toolchain(tree, "0000000\n")
    subprocess.run(["make", "-s", "-C", tree, stamp], check=True)
    assert not compiler.exists()
    assert stamp.read_text() == version


@spec(CAPABILITY, "One toolchain for every board", "A toolchain built for a board")
@pytest.mark.parametrize(
    ("record", "refusal"),
    [pytest.param(record, refusal, id=name) for name, record, refusal in _board_toolchains()],
)
def test_a_board_toolchain_is_refused(
    record: dict[str, str] | None, refusal: str | None, tmp_path: Path
) -> None:
    board = load_all()[0]
    tree = _tree_with_toolchain(tmp_path, board, record)
    result = subprocess.run(
        [REPO / "scripts" / "build.sh", board.id],
        env={**os.environ, "WRT_WORKDIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    # A refused toolchain stops the build before anything is built; a
    # board-neutral one lets it start.
    assert (tree / "built").exists() == (refusal is None), result.stderr
    if refusal is not None:
        assert result.returncode != 0
        assert refusal in result.stderr
        assert "just toolchain-build" in result.stderr
