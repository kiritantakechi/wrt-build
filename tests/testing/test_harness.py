"""testing/harness: scenarios map to tests, both targets share the suite, uv pins Python."""

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from wrt_tests import spec

CAPABILITY = "testing/harness"
TESTS_DIR = Path(__file__).resolve().parents[1]
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
        *("-m", "wrt_tests.coverage"),
        *("--openspec", str(openspec), "--tests", str(tests)),
        *args,
        cwd=tests,
    )


@spec(CAPABILITY, "规格场景与测试一一对应", "生成覆盖报告")
def test_coverage_report(demo: tuple[Path, Path]) -> None:
    result = _coverage(*demo, "--change", "demo-change")
    assert "covered    demo/widget / Demo / covered one  demo/test_widget.py::test_covered" in (
        result.stdout
    )
    assert "MISSING    demo/widget / Demo / missing one" in result.stdout
    assert "demo-change: no test for demo/widget / Demo / missing one" in result.stderr
    assert result.returncode == 1


@spec(CAPABILITY, "规格场景与测试一一对应", "标记指向不存在的场景")
def test_dangling_marker_fails(demo: tuple[Path, Path]) -> None:
    openspec, tests = demo
    module = tests / "demo" / "test_widget.py"
    module.write_text(module.read_text().replace("covered one", "no such scenario"))
    result = _coverage(openspec, tests)
    assert result.returncode == 1
    assert "demo/test_widget.py::test_covered: @spec names no scenario" in result.stderr


@spec(CAPABILITY, "同一套用例，两种目标", "分别在两种目标上运行")
def test_both_targets_collect_the_same_tests() -> None:
    collected = [
        _python("-m", "pytest", "--collect-only", "-q", "--target-kind", kind, cwd=TESTS_DIR)
        for kind in ("emulation", "device")
    ]
    ids = [{line for line in run.stdout.splitlines() if "::" in line} for run in collected]
    assert ids[0]
    assert ids[0] == ids[1]


@spec(CAPABILITY, "目标专属用例要注明原因", "在模拟器上运行仅真机用例")
def test_device_only_tests_are_skipped_with_reason(tmp_path: Path) -> None:
    (tmp_path / "test_probe.py").write_text(
        "from wrt_tests import target\n\n\n"
        '@target("device", "needs the real SD card slot")\n'
        "def test_probe() -> None:\n    pass\n"
    )
    result = _python(
        *("-m", "pytest", "-p", "wrt_tests.plugin", "--target-kind", "emulation", "-rs"),
        *("--rootdir", str(tmp_path), str(tmp_path)),
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout
    assert "1 skipped" in result.stdout
    assert "device only: needs the real SD card slot" in result.stdout


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


@spec(CAPABILITY, "Python 工具链由 uv 锁定", "锁文件与声明不一致")
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


@spec(CAPABILITY, "Python 工具链由 uv 锁定", "类型错误")
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
