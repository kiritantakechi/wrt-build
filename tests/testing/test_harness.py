"""testing/harness: scenarios and tests, the toolchain, data schemas, waits, failure reports."""

import json
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Literal, cast

import pytest

from wrt_tests import spec
from wrt_tests.model.boards import BOARDS_DIR, Description
from wrt_tests.model.coverage import VerifiedElsewhere
from wrt_tests.model.data import DataError, read_json, read_toml
from wrt_tests.model.outputs import EmulationSource, Manifest, Release, ToolchainRecord
from wrt_tests.model.poll import until
from wrt_tests.model.undefined_behavior import Diagnostic, Review
from wrt_tests.services.fixtures import pytest_runtest_makereport

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import BaseModel

    from wrt_tests.device.router import Router
    from wrt_tests.services.datapath import Online

CAPABILITY = "testing/harness"
TESTS_DIR = Path(__file__).resolve().parents[1]
FIXTURES = TESTS_DIR / "fixtures"
DEMO_SPEC = """## ADDED Requirements

### Requirement: Demo
#### Scenario: covered one
- **WHEN** a
- **THEN** b

#### Scenario: missing one
- **WHEN** a
- **THEN** b
"""
COVERED_TEST = """from wrt_tests import spec


@spec("demo/widget", "Demo", "covered one")
def test_covered() -> None:
    pass
"""


def _python(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def _tool(name: str) -> str:
    """Path of a tool installed in the tests' virtual environment."""
    return str(Path(sys.executable).with_name(name))


@pytest.fixture
def demo(tmp_path: Path) -> tuple[Path, Path]:
    """Return an OpenSpec tree with one change and a tests tree covering half of it."""
    openspec = tmp_path / "openspec"
    (openspec / "specs").mkdir(parents=True)
    spec_file = openspec / "changes" / "demo-change" / "specs" / "demo" / "widget" / "spec.md"
    spec_file.parent.mkdir(parents=True)
    spec_file.write_text(DEMO_SPEC)
    tests = tmp_path / "tests"
    (tests / "demo").mkdir(parents=True)
    (tests / "demo" / "test_widget.py").write_text(COVERED_TEST)
    return openspec, tests


def _coverage(openspec: Path, tests: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _python(
        *("-m", "wrt_tests.model.coverage"),
        *("--openspec", str(openspec), "--tests", str(tests)),
        *args,
        cwd=tests,
    )


@spec(CAPABILITY, "One test per spec scenario", "Generate coverage report")
def test_coverage_report(demo: tuple[Path, Path]) -> None:
    openspec, tests = demo
    result = _coverage(openspec, tests, "--change", "demo-change")
    assert "covered    demo/widget / Demo / covered one  demo/test_widget.py::test_covered" in (
        result.stdout
    )
    assert "MISSING    demo/widget / Demo / missing one" in result.stdout
    assert "demo-change: no test for demo/widget / Demo / missing one" in result.stderr
    assert result.returncode == 1
    # Archived, the spec is the system as built: its scenarios need their tests
    # without being named.
    change = openspec / "changes" / "demo-change"
    (change / "specs" / "demo").rename(openspec / "specs" / "demo")
    shutil.rmtree(change)
    archived = _coverage(openspec, tests)
    assert "MISSING    demo/widget / Demo / missing one" in archived.stdout
    assert "error: no test for demo/widget / Demo / missing one" in archived.stderr
    assert archived.returncode == 1


@spec(CAPABILITY, "One test per spec scenario", "Marker names a missing scenario")
def test_dangling_marker_fails(demo: tuple[Path, Path]) -> None:
    openspec, tests = demo
    module = tests / "demo" / "test_widget.py"
    module.write_text(module.read_text().replace("covered one", "no such scenario"))
    result = _coverage(openspec, tests)
    assert result.returncode == 1
    assert "demo/test_widget.py::test_covered: @spec names no scenario" in result.stderr


def _wheel(directory: Path, name: str) -> Path:
    """Write a minimal pure-Python wheel of ``name`` 1.0 and return its path."""
    wheel = directory / f"{name}-1.0-py3-none-any.whl"
    dist_info = f"{name}-1.0.dist-info"
    files = {
        f"{name}/__init__.py": "",
        f"{dist_info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n",
        f"{dist_info}/WHEEL": "Wheel-Version: 1.0\nGenerator: wrt-tests\nRoot-Is-Purelib: true\n"
        "Tag: py3-none-any\n",
    }
    record = "".join(f"{path},,\n" for path in files) + f"{dist_info}/RECORD,,\n"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
        archive.writestr(f"{dist_info}/RECORD", record)
    return wheel


@spec(CAPABILITY, "Fixtures by layer", "Fixture defined in the root configuration")
def test_a_fixture_in_the_root_configuration_fails(demo: tuple[Path, Path]) -> None:
    openspec, tests = demo
    shutil.copytree(TESTS_DIR / "wrt_tests", tests / "wrt_tests")
    (tests / "conftest.py").write_text(
        "import pytest\n\n\n@pytest.fixture(scope='session')\ndef local() -> int:\n    return 1\n"
    )
    result = _coverage(openspec, tests)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "conftest.py: defines the fixture local" in output, output


@spec(CAPABILITY, "Python toolchain locked by uv", "Lock file out of sync")
def test_stale_lock_is_rejected(tmp_path: Path) -> None:
    # Every script syncs or runs the tests project in locked mode ...
    scripts = (TESTS_DIR.parent / "scripts").glob("*.sh")
    uv_calls = [
        line
        for path in scripts
        for line in path.read_text().splitlines()
        if re.search(r"\buv (sync|run)\b", line) and "--no-sync" not in line
    ]
    assert uv_calls
    assert all("--locked" in line for line in uv_calls), uv_calls
    # ... and locked mode refuses a declaration the lock does not match. The project
    # is self-contained (a local wheel), so this holds without any network.
    project = tmp_path / "project"
    project.mkdir()
    pyproject = project / "pyproject.toml"
    pyproject.write_text('[project]\nname = "probe-project"\nversion = "0"\ndependencies = []\n')
    uv = ("uv", "--offline", "--directory", str(project))
    subprocess.run([*uv, "lock"], check=True, capture_output=True)
    wheel = _wheel(tmp_path, "probe")
    pyproject.write_text(pyproject.read_text().replace("[]", f'["probe @ {wheel.as_uri()}"]'))
    result = subprocess.run([*uv, "sync", "--locked"], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "needs to be updated" in result.stderr


@spec(CAPABILITY, "Python toolchain locked by uv", "Type error")
def test_type_error_is_reported(tmp_path: Path) -> None:
    shutil.copy(TESTS_DIR / "ty.toml", tmp_path / "ty.toml")
    (tmp_path / "broken.py").write_text('count: int = "three"\n')
    result = subprocess.run(
        [_tool("ty"), "check", "--output-format", "concise", "broken.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "broken.py:1:" in result.stdout


def _break(entry: dict[str, object], breakage: str) -> str:
    """Break ``entry`` in place; return the field that is wrong now."""
    if breakage == "unknown field":
        entry["colour"] = "red"
        return "colour"
    field = next(key for key, value in entry.items() if isinstance(value, str))
    entry[field] = 1
    return field


@dataclass(frozen=True, slots=True)
class _JsonFile:
    """A JSON data file the tests read, and how: one document, or a list of entries."""

    path: Path
    read: Callable[[Path], BaseModel | list[BaseModel]]

    def break_into(self, copy: Path, breakage: str) -> str:
        """Write a copy of the file with ``breakage``; return where its problem lies."""
        match self.read(self.path):
            case list() as entries:
                dumped = [entry.model_dump(mode="json") for entry in entries]
                where = f"[0]: {_break(dumped[0], breakage)}"
                copy.write_text(json.dumps(dumped), encoding="utf-8")
            case document:
                dumped = document.model_dump(mode="json")
                where = _break(dumped, breakage)
                copy.write_text(json.dumps(dumped), encoding="utf-8")
        return where


@dataclass(frozen=True, slots=True)
class _TomlFile:
    """A TOML data file the tests read: the entries of one array of tables."""

    path: Path
    table: str
    model: type[BaseModel]

    def read(self, path: Path) -> list[BaseModel]:
        """Read ``path`` as this file is read."""
        return list(read_toml(path, self.table, self.model))

    def break_into(self, copy: Path, breakage: str) -> str:
        """Write a copy of the file with ``breakage`` in its first entry; return where."""
        text = self.path.read_text(encoding="utf-8")
        header = re.search(rf"^\[\[{self.table}\]\]\n", text, re.MULTILINE)
        assert header, self.path
        head, entry = text[: header.end()], text[header.end() :]
        if breakage == "unknown field":
            field, entry = "colour", f'colour = "red"\n{entry}'
        else:
            line = re.search(r'^(\w+) = ".*"$', entry, re.MULTILINE)
            assert line, self.path
            field = line.group(1)
            entry = f"{entry[: line.start()]}{field} = 1{entry[line.end() :]}"
        copy.write_text(head + entry, encoding="utf-8")
        return f"{self.table}[0]: {field}"


# Every data file the tests read (module-boundaries D7), a real one of each.
DATA_FILES = {
    "board description": _JsonFile(BOARDS_DIR / "r4s.json", lambda p: read_json(p, Description)),
    "verified elsewhere": _TomlFile(
        TESTS_DIR / "verified-elsewhere.toml", "scenario", VerifiedElsewhere
    ),
    "reviewed warnings": _TomlFile(TESTS_DIR / "reviewed-warnings.toml", "warning", Review),
    "manifest": _JsonFile(FIXTURES / "manifest.json", lambda p: read_json(p, Manifest)),
    "warnings report": _JsonFile(
        FIXTURES / "warnings.json", lambda p: list(read_json(p, list[Diagnostic]))
    ),
    "emulation source": _JsonFile(
        FIXTURES / "source.json", lambda p: read_json(p, EmulationSource)
    ),
    "toolchain record": _JsonFile(
        FIXTURES / "wrt-toolchain.json", lambda p: read_json(p, ToolchainRecord)
    ),
    "release": _JsonFile(FIXTURES / "release.json", lambda p: read_json(p, Release)),
}


@spec(CAPABILITY, "One schema per data file", "Malformed data file")
@pytest.mark.parametrize("breakage", ["unknown field", "wrong type"])
@pytest.mark.parametrize("name", DATA_FILES)
def test_a_malformed_data_file_names_the_field(name: str, breakage: str, tmp_path: Path) -> None:
    data = DATA_FILES[name]
    copy = tmp_path / data.path.name
    where = data.break_into(copy, breakage)
    with pytest.raises(DataError) as error:
        data.read(copy)
    problems = error.value.problems
    assert any(problem.startswith(f"{copy}: {where}: ") for problem in problems), problems


# Every kind of empty answer a probe may give while its condition does not hold.
EMPTY_ANSWERS = (None, False, 0, "", (), frozenset())


def _answers(*answers: object) -> Callable[[], object]:
    """Return a probe that gives ``answers`` one by one, then the last for ever."""
    remaining = list(answers)
    return lambda: remaining.pop(0) if len(remaining) > 1 else remaining[0]


@spec(CAPABILITY, "Waiting for a condition", "A probe answers empty first")
def test_a_wait_goes_on_through_empty_answers() -> None:
    assert until(_answers("", [], "listening"), timeout=5, what="an answer", every=0) == "listening"


@spec(CAPABILITY, "Waiting for a condition", "No answer within the time limit")
def test_a_wait_without_an_answer_names_what_it_waited_for() -> None:
    with pytest.raises(TimeoutError, match=re.escape("no listener within 0.2 s")):
        until(_answers(*EMPTY_ANSWERS), timeout=0.2, what="listener", every=0.01)


# A detached command that ends without the reboot the harness then waits for.
NEVER_REBOOTING = "this command ends without a reboot"
SECTION = re.compile(r"(?ms)^--- (.+?)\n(.*?)(?=^--- |\Z)")


@spec(CAPABILITY, "Failures name the router's state", "A reboot that does not come")
def test_a_reboot_that_does_not_come_names_its_command(router: Router) -> None:
    previous_boot = router.boot_id()
    command = f"echo '{NEVER_REBOOTING}'; exit 3"
    router.detach(command)
    with pytest.raises(TimeoutError) as raised:
        router.wait_rebooted(previous_boot, timeout=10)
    command_note, output_note, console_note = raised.value.__notes__
    assert command_note == f"the reboot was to follow: {command}"
    assert output_note == f"its output, at {router.address}:\n{NEVER_REBOOTING}"
    assert console_note.startswith("the console since:")


def _call_report(item: object, outcome: Literal["passed", "failed"]) -> pytest.TestReport:
    """Return what the services layer's report hook makes of a call's report on ``item``."""
    report = pytest.TestReport("demo", ("demo", 0, "demo"), {}, outcome, None, "call")
    call = pytest.CallInfo.from_call(lambda: None, "call")
    hook = pytest_runtest_makereport(cast("pytest.Item", item), call)
    next(hook)
    try:
        hook.send(report)
    except StopIteration as stopped:
        return cast("pytest.TestReport", stopped.value)
    msg = "the report hook did not return a report"
    raise AssertionError(msg)


@spec(CAPABILITY, "Failures name the router's state", "A failing test with the router online")
def test_a_failing_online_test_names_the_datapath(online: Online) -> None:
    item = SimpleNamespace(funcargs={"online": online})
    sections = dict(_call_report(item, "failed").sections)
    parts = dict(SECTION.findall(sections["datapath"]))
    assert "default via " in parts["client-a$ ip -6 route"]
    assert '"up": true' in parts["router$ ifstatus wan"]
    assert online.session.interface in parts["ISP sessions"]
    assert parts["ISP pppd log"].strip()
    assert _call_report(item, "passed").sections == []
