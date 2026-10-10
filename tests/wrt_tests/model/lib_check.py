"""lib-check: the scripts load what they call, and the library has no dead function.

The shell library is modules by domain (``scripts/lib/*.sh``, module-boundaries
D1). A script loads core by path and the other modules by name, with ``use``; a
module loads the modules it depends on with its own ``use``. ``lib-check``
(``just check modules``, D4) reads them all and fails on

* a call of a library function that the modules a script or a module loads,
  directly or through theirs, do not provide;
* a library function that no script, other module, test, workflow or recipe
  calls.

Each problem names the file and the function. A call is the function's name as
a word outside comments; every library function has a name of its own.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from wrt_tests.model.repository import REPO_DIR

CORE = "core"
CORE_LINE = '. "$(dirname -- "$0")/lib/core.sh"'
FUNCTION = re.compile(r"^([a-z_][a-z0-9_]*)\(\) [({]$", re.MULTILINE)
USE = re.compile(r"^\s*use ([a-z ]+)$", re.MULTILINE)
WORD = re.compile(r"\b[a-z_][a-z0-9_]*\b")
COMMENT = re.compile(r"(^|\s)#.*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Module:
    """A library module: the functions it defines, and the modules it loads."""

    name: str
    path: Path
    functions: frozenset[str]
    uses: frozenset[str]


def _code(text: str) -> str:
    """Return ``text`` without its comments."""
    return COMMENT.sub(r"\1", text)


def _uses(text: str) -> frozenset[str]:
    """Return the modules the ``use`` lines of ``text`` name."""
    lines = [str(match[1]) for match in USE.finditer(_code(text))]
    return frozenset(name for line in lines for name in line.split())


def read_modules(library: Path) -> dict[str, Module]:
    """Return the modules of ``library``, by name."""
    modules = {}
    for path in sorted(library.glob("*.sh")):
        text = path.read_text(encoding="utf-8")
        functions = frozenset(FUNCTION.findall(text))
        modules[path.stem] = Module(path.stem, path, functions, _uses(text))
    return modules


def _loaded(modules: dict[str, Module], names: frozenset[str]) -> set[str]:
    """Return ``names`` and every module they load, transitively."""
    loaded: set[str] = set()
    todo = [*names]
    while todo:
        name = todo.pop()
        if name not in loaded and name in modules:
            loaded.add(name)
            todo += modules[name].uses
    return loaded


def _calls(text: str, functions: set[str]) -> set[str]:
    """Return the library functions ``text`` calls."""
    return {str(match[0]) for match in WORD.finditer(_code(text))} & functions


def missing_loads(repo: Path) -> list[str]:
    """Return the calls of library functions that the caller's loaded modules do not provide."""
    modules = read_modules(repo / "scripts" / "lib")
    every = {function for module in modules.values() for function in module.functions}
    owner = {function: module.name for module in modules.values() for function in module.functions}
    callers: list[tuple[Path, frozenset[str]]] = []
    for script in sorted((repo / "scripts").glob("*.sh")):
        text = script.read_text(encoding="utf-8")
        loads = _uses(text) | ({CORE} if CORE_LINE in text else set())
        callers.append((script, frozenset(loads)))
    callers += [(module.path, module.uses | {CORE, module.name}) for module in modules.values()]
    problems: list[str] = []
    for path, loads in callers:
        loaded = _loaded(modules, loads)
        provided = {function for name in loaded for function in modules[name].functions}
        unknown = sorted(loads - set(modules))
        problems += [f"{path.relative_to(repo)}: use names no module {name}" for name in unknown]
        problems += [
            f"{path.relative_to(repo)}: calls {function} without loading {owner[function]}"
            for function in sorted(_calls(path.read_text(encoding="utf-8"), every) - provided)
        ]
    return problems


def dead_functions(repo: Path) -> list[str]:
    """Return the library functions that no script, other module, test or recipe calls."""
    modules = read_modules(repo / "scripts" / "lib")
    texts = [_code(path.read_text(encoding="utf-8")) for path in (repo / "scripts").glob("*.sh")]
    texts += [
        path.read_text(encoding="utf-8")
        for path in [
            *(repo / "tests").rglob("*.py"),
            *(repo / ".github" / "workflows").glob("*.yml"),
            repo / "justfile",
        ]
        if not any(part.startswith(".venv") for part in path.parts)
    ]
    problems = []
    for module in modules.values():
        own = _code(module.path.read_text(encoding="utf-8"))
        others = [
            _code(m.path.read_text(encoding="utf-8")) for m in modules.values() if m != module
        ]
        for function in sorted(module.functions):
            word = re.compile(rf"\b{function}\b")
            # Its own module calls it when the name appears beyond its definition.
            called = len(word.findall(own)) > 1 or any(word.search(t) for t in (*others, *texts))
            if not called:
                problems.append(f"{module.path.relative_to(repo)}: nothing calls {function}")
    return problems


def main(argv: list[str] | None = None) -> int:
    """Check the shell library's loads and callers; print each problem."""
    parser = argparse.ArgumentParser(prog="lib-check", description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=REPO_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    problems = missing_loads(args.repo) + dead_functions(args.repo)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
