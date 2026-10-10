"""The UB-indicative warnings, collected and reviewed (toolchain-o3 D4).

The build collects them from its logs (scripts/lib.sh); the system tests check
them against the register (wrt_tests.model.undefined_behavior).
"""

import json
import os
import subprocess
from datetime import date
from pathlib import Path

import pytest

from wrt_tests.model.undefined_behavior import (
    Diagnostic,
    Review,
    load_register,
    load_report,
    stale,
    unreviewed,
)

LIB = Path(__file__).resolve().parents[2] / "scripts" / "lib.sh"
BUILD = "/work/openwrt/build_dir/target-aarch64_generic_musl_r4s"
TOOLCHAIN = "/work/openwrt/staging_dir/toolchain-aarch64_generic_gcc-15.3.0_musl"


def _lib(function: str, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a function of lib.sh with ``args`` in ``cwd``."""
    return subprocess.run(
        ["sh", "-c", f'. "{LIB}" && {function} "$@"', "sh", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _warnings(tmp_path: Path, log: str) -> list[tuple[str, ...]]:
    """Return what ub_warnings finds in ``log``: option, file, function and line."""
    (tmp_path / "compile.txt").write_text(log)
    result = _lib("ub_warnings", "compile.txt", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    return [tuple(line.split("\t")) for line in result.stdout.splitlines()]


def test_a_warning_falls_in_the_function_named_before_it(tmp_path: Path) -> None:
    # GCC names a function once, before its first diagnostic, in typographic quotes
    # in a UTF-8 locale; notes and source excerpts do not end it.
    log = """\
make[5]: Entering directory '/work/openwrt/build_dir/target-aarch64_generic_musl_r4s/pptp-1.10.0'
pptp.c: In function 'pptp_start_client':
pptp.c:185:60: warning: taking address of packed member of 'struct sockaddr_pppox' \
may result in an unaligned pointer value [-Waddress-of-packed-member]
  185 |         if (connect(fd, (struct sockaddr *)&sp, sizeof(sp)) < 0) {
      |                                                            ^
pptp.c:201:9: warning: 'len' may be used uninitialized [-Wmaybe-uninitialized]
pptp.c:180:13: note: 'len' was declared here
lexer.c: In function \N{LEFT SINGLE QUOTATION MARK}next_token\N{RIGHT SINGLE QUOTATION MARK}:
lexer.c:9:3: warning: left shift count >= width of type [-Wshift-count-overflow]
"""
    assert _warnings(tmp_path, log) == [
        ("-Waddress-of-packed-member", "pptp.c", "pptp_start_client", "185"),
        ("-Wmaybe-uninitialized", "pptp.c", "pptp_start_client", "201"),
        ("-Wshift-count-overflow", "lexer.c", "next_token", "9"),
    ]


def test_a_warning_outside_any_function_names_none(tmp_path: Path) -> None:
    # "At top level", or a file other than the function's: a later compilation,
    # which GCC gives no context line of its own.
    log = """\
util.c: In function 'grow':
util.c:40:3: warning: pointer 'p' used after 'free' [-Wuse-after-free]
table.c: At top level:
table.c:12:1: warning: 'n' is used uninitialized [-Wuninitialized]
other.c:7:5: warning: 'm' is used uninitialized [-Wuninitialized]
"""
    assert _warnings(tmp_path, log) == [
        ("-Wuninitialized", "other.c", "", "7"),
        ("-Wuninitialized", "table.c", "", "12"),
        ("-Wuse-after-free", "util.c", "grow", "40"),
    ]


def test_inlined_code_is_placed_at_its_outermost_call(tmp_path: Path) -> None:
    # GCC continues the context line with the chain of calls the code was inlined
    # through, the outermost last; a later warning of that function, in its file,
    # falls in it as well.
    log = f"""\
In file included from {TOOLCHAIN}/include/string.h:12,
                 from ../libbpf/src/btf.c:3:
In function 'btf_add_type',
    inlined from 'btf__add_btf' at ../libbpf/src/btf.c:1802:8,
    inlined from 'bpf_object_load.constprop' at ../libbpf/src/libbpf.c:8960:9:
../libbpf/src/btf.c:1170:27: warning: 'sz' may be used uninitialized [-Wmaybe-uninitialized]
../libbpf/src/libbpf.c:8970:5: warning: 'fd' may be used uninitialized [-Wmaybe-uninitialized]
"""
    assert _warnings(tmp_path, log) == [
        ("-Wmaybe-uninitialized", "libbpf/src/libbpf.c", "bpf_object_load", "8960"),
        ("-Wmaybe-uninitialized", "libbpf/src/libbpf.c", "bpf_object_load", "8970"),
    ]


def test_a_note_takes_the_context_before_it(tmp_path: Path) -> None:
    # GCC gives a note the chain of the code it points to; the warning after it
    # has a context of its own, or none.
    log = """\
In function 'xmalloc',
    inlined from 'yyparse' at parse.y:1099:9:
xmalloc.c:42:3: note: by argument 1 of type 'size_t'
execute_cmd.c:1197:7: warning: 'ofifo_list' may be used uninitialized [-Wmaybe-uninitialized]
"""
    assert _warnings(tmp_path, log) == [
        ("-Wmaybe-uninitialized", "execute_cmd.c", "", "1197"),
    ]


def test_an_interleaved_chain_is_dropped(tmp_path: Path) -> None:
    # Jobs that write to the log at the same time interleave: before patch 0016
    # synced a package's jobs, bash's R4S build put another LTRANS job's chain
    # and context lines before redir.c's warning.
    log = """\
In function 'make_command',
    inlined from 'make_group_command' at make_cmd.c:321:11,
    inlined from 'yyparse' at parse.y:1198:24:
execute_cmd.c: In function 'execute_command_internal':
redir.c: In function 'do_redirection_internal.constprop':
redir.c:872:23: warning: 'new_redirect' may be used uninitialized [-Wmaybe-uninitialized]
"""
    assert _warnings(tmp_path, log) == [
        ("-Wmaybe-uninitialized", "redir.c", "do_redirection_internal", "872"),
    ]


def test_an_option_with_a_value_is_named_without_it(tmp_path: Path) -> None:
    # GCC names an option that takes a level with a trailing "=".
    log = """\
table.c: In function 'lookup':
table.c:30:12: warning: array subscript 4 is above array bounds of 'int[4]' [-Warray-bounds=]
"""
    assert _warnings(tmp_path, log) == [("-Warray-bounds", "table.c", "lookup", "30")]


def test_only_ub_indicative_warnings_count(tmp_path: Path) -> None:
    # Style warnings, and errors (which fail the build anyway), are not recorded;
    # a warning reported twice (a header of two compilations) is recorded once.
    log = """\
main.c: In function 'main':
main.c:3:9: warning: unused variable 'x' [-Wunused-variable]
main.c:4:1: error: array subscript 9 is outside array bounds [-Werror=array-bounds=]
main.c:5:3: warning: 'v' may be used uninitialized [-Wmaybe-uninitialized]
main.c: In function 'main':
main.c:5:3: warning: 'v' may be used uninitialized [-Wmaybe-uninitialized]
"""
    assert _warnings(tmp_path, log) == [("-Wmaybe-uninitialized", "main.c", "main", "5")]


def test_a_clone_is_named_after_its_function(tmp_path: Path) -> None:
    # GCC names the clones it makes (.isra, .part, .constprop) after the source's
    # function, with suffixes that follow the optimization, and the board's -mcpu.
    log = """\
src/load.c: In function 'lex_scan.isra':
src/load.c:573:9: warning: writing 1 byte into a region of size 0 [-Wstringop-overflow=]
segment.c: In function 'f2fs_build_file.constprop.isra':
segment.c:495:3: warning: 'blk' may be used uninitialized [-Wmaybe-uninitialized]
"""
    assert _warnings(tmp_path, log) == [
        ("-Wmaybe-uninitialized", "segment.c", "f2fs_build_file", "495"),
        ("-Wstringop-overflow", "src/load.c", "lex_scan", "573"),
    ]


def test_paths_lose_the_build_directories(tmp_path: Path) -> None:
    # The package's build directory (a build variant's with the versioned one inside
    # it), the staging directory and ./ parts: both boards, every checkout and every
    # version name the same file alike.
    cache = f"{BUILD}/dnsmasq-nodhcpv6/dnsmasq-2.93/src/cache.c"
    log = f"""\
{cache}: In function 'cache_insert':
{cache}:88:7: warning: writing 8 bytes into a region of size 4 [-Wstringop-overflow=]
{BUILD}/ubus-2026.06.28/libubus.c:12:3: warning: 'r' is used uninitialized [-Wuninitialized]
{TOOLCHAIN}/include/fortify/string.h:40:10: warning: reading 9 bytes [-Wstringop-overread]
ncurses/./base/lib_getch.c:477:5: warning: 'buf' may be used uninitialized [-Wmaybe-uninitialized]
"""
    assert _warnings(tmp_path, log) == [
        ("-Wmaybe-uninitialized", "ncurses/base/lib_getch.c", "", "477"),
        ("-Wstringop-overflow", "src/cache.c", "cache_insert", "88"),
        ("-Wstringop-overread", "include/fortify/string.h", "", "40"),
        ("-Wuninitialized", "libubus.c", "", "12"),
    ]


PACKAGEINFO = """\
Source-Makefile: package/network/services/ppp/Makefile

Package: ppp
Version: 2.5.3-r2
Build-Variant: default
@@

Package: ppp-multilink
Build-Variant: multilink
@@

Package: ppp-mod-pppoe
Description: PPPoE support
@@

Source-Makefile: package/libs/libbpf/Makefile

Package: libbpf
ABI-Version: 1
@@

Source-Makefile: package/feeds/packages/curl/Makefile

Package: curl
@@

Package: libcurl
ABI-Version: 4
@@
"""


def test_image_packages_map_to_their_build_logs(tmp_path: Path) -> None:
    # A library is installed under its ABI version; a package of no build variant
    # is built in the variant builds of the image's other packages from its source;
    # the kernel is the target's.
    (tmp_path / "manifest").write_text(
        "curl - 8.16.0-r1\nkernel - 6.18.52~96aa-r1\nlibbpf1 - 1.6.2-r1\n"
        "libcurl4 - 8.16.0-r1\nppp - 2.5.3-r2\nppp-mod-pppoe - 2.5.3-r2\n"
    )
    (tmp_path / "packageinfo").write_text(PACKAGEINFO)
    result = _lib("image_logs", "manifest", "packageinfo", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "curl\tpackage/feeds/packages/curl",
        "libbpf\tpackage/libs/libbpf",
        "ppp\tpackage/network/services/ppp/default",
    ]


def test_a_package_without_metadata_fails(tmp_path: Path) -> None:
    (tmp_path / "manifest").write_text("curl - 8.16.0-r1\nlibbpf - 1.6.2-r1\n")
    (tmp_path / "packageinfo").write_text(PACKAGEINFO)
    result = _lib("image_logs", "manifest", "packageinfo", cwd=tmp_path)
    assert result.returncode != 0
    assert "no package metadata for libbpf" in result.stderr


def test_a_step_that_did_nothing_keeps_the_record(tmp_path: Path) -> None:
    # OpenWrt rewrites the log of every package whose compile step it runs, also of
    # one it finds up to date, with nothing but make's time line.
    logs, records = tmp_path / "logs", tmp_path / "records"
    built, idle, old = (
        logs / "package" / name / "compile.txt" for name in ("built", "idle", "old")
    )
    for log in (built, idle, old):
        log.parent.mkdir(parents=True)
    old.write_text("old.c:1:1: warning: 'o' is used uninitialized [-Wuninitialized]\n")
    os.utime(old, (1_700_000_000, 1_700_000_000))
    record = records / "package" / "idle" / "compile.tsv"
    record.parent.mkdir(parents=True)
    record.write_text("-Wuninitialized\tidle.c\t\t3\n")
    since = tmp_path / "since"
    since.touch()
    os.utime(since, (1_700_000_100, 1_700_000_100))
    built.write_text("built.c:2:1: warning: 'b' is used uninitialized [-Wuninitialized]\n")
    idle.write_text("time: package/idle/compile#0.07#0.02#0.16\n")

    result = _lib("warnings_harvest", str(logs), str(records), str(since), cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert (records / "package" / "built" / "compile.tsv").read_text() == (
        "-Wuninitialized\tbuilt.c\t\t2\n"
    )
    assert record.read_text() == "-Wuninitialized\tidle.c\t\t3\n"
    assert not (records / "package" / "old").exists()


def test_a_package_that_compiles_without_a_word_gets_an_empty_record(tmp_path: Path) -> None:
    # base-files compiles silently: its first log holds only make's time line too,
    # and the image's report needs a record of every package it ships.
    logs, records = tmp_path / "logs", tmp_path / "records"
    since = tmp_path / "since"
    since.touch()
    os.utime(since, (1_700_000_000, 1_700_000_000))
    log = logs / "package" / "base-files" / "compile.txt"
    log.parent.mkdir(parents=True)
    log.write_text("time: package/base-files/compile#0.61#0.39#1.19\n")

    result = _lib("warnings_harvest", str(logs), str(records), str(since), cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert (records / "package" / "base-files" / "compile.tsv").read_text() == ""


PACKED = {
    "package": "ppp",
    "option": "-Waddress-of-packed-member",
    "file": "pptp.c",
    "function": "pptp_start_client",
}


def _review(**fields: object) -> Review:
    return Review.model_validate(
        {
            **PACKED,
            "reason": "the member is aligned",
            "reviewed": date(2026, 10, 5),
            **fields,
        }
    )


def test_the_report_is_read_from_the_build(tmp_path: Path) -> None:
    (tmp_path / "warnings.json").write_text(json.dumps([{**PACKED, "line": 185}]))
    assert load_report(tmp_path) == [Diagnostic.model_validate({**PACKED, "line": 185})]


def test_a_review_covers_its_warning_on_any_line() -> None:
    # Upstream moving code around moves the line, not the package, option, file or
    # function; a warning in another function is another warning.
    moved = Diagnostic.model_validate({**PACKED, "line": 240})
    other = Diagnostic.model_validate({**PACKED, "function": "pptp_call", "line": 92})
    register = [_review()]
    found = unreviewed([moved, other], register, "r4s")
    assert [str(warning) for warning in found] == [
        "ppp: -Waddress-of-packed-member at pptp.c:92, function pptp_call"
    ]
    assert stale(register, [moved, other], "r4s") == []


def test_a_review_that_matches_nothing_is_stale() -> None:
    gone = _review(file="pppoe.c", function="")
    assert [str(review) for review in stale([gone], [], "r4s")] == [
        "ppp: -Waddress-of-packed-member in pppoe.c"
    ]


def test_a_review_for_other_boards_neither_covers_nor_goes_stale() -> None:
    warning = Diagnostic.model_validate({**PACKED, "line": 185})
    register = [_review(boards=["r6s"])]
    assert unreviewed([warning], register, "r4s") == [warning]
    assert stale(register, [], "r4s") == []
    assert unreviewed([warning], register, "r6s") == []
    assert [str(review) for review in stale(register, [], "r6s")] == [
        "ppp: -Waddress-of-packed-member in pptp.c, function pptp_start_client"
    ]


@pytest.mark.parametrize(
    ("entries", "error"),
    [
        pytest.param([{"boards": ["r5s"]}], "names unknown boards: r5s", id="unknown board"),
        pytest.param([{}, {"reason": "again"}], "is reviewed twice", id="twice"),
    ],
)
def test_the_register_names_known_boards_and_each_warning_once(
    entries: list[dict[str, object]], error: str, tmp_path: Path
) -> None:
    register = tmp_path / "reviewed-warnings.toml"
    tables = []
    for entry in entries:
        fields: dict[str, object] = {
            **PACKED,
            "reason": "the member is aligned",
            "reviewed": "2026-10-05",
            **entry,
        }
        lines = [
            f"{name} = {value}" if name == "reviewed" else f"{name} = {json.dumps(value)}"
            for name, value in fields.items()
        ]
        tables.append("[[warning]]\n" + "\n".join(lines) + "\n")
    register.write_text("\n".join(tables))
    with pytest.raises(ValueError, match=error):
        load_register(register)


def test_the_register_is_valid() -> None:
    load_register()
