"""Run a CI script against a stand-in gh that answers for a repository described as data.

The stand-in answers the gh calls of scripts/cache-room.sh and scripts/cache-prune.sh
(build-integrity D5, D6; release-integrity D6) as GitHub's API would for the
repository, and deletes the caches they delete from it, so that a test reads which
caches are left.
"""

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from wrt_tests.model.repository import REPO_DIR

if TYPE_CHECKING:
    from pathlib import Path

SCRIPTS = REPO_DIR / "scripts"
REPOSITORY = "owner/repository"
MAIN = "refs/heads/main"
# The stand-in, which keeps the repository in github.json beside itself.
GH = f"""#!{sys.executable} -I
import json, subprocess, sys
from pathlib import Path

described = Path(__file__).with_name("github.json")
github = json.loads(described.read_text())
args = sys.argv[1:]


def option(name):
    return args[args.index(name) + 1] if name in args else None


def answer(value):
    jq = option("--jq")
    if jq is None:
        print(json.dumps(value))
    else:
        subprocess.run(["jq", "-r", jq], input=json.dumps(value), text=True, check=True)


def caches(ref):
    found = [cache for cache in github["caches"] if ref is None or cache["ref"] == ref]
    return sorted(found, key=lambda cache: cache["id"], reverse=True)


match args[:2]:
    case ["cache", "list"]:
        answer(caches(option("--ref")))
    case ["cache", "delete"] if "--all" in args:
        gone = {{cache["id"] for cache in caches(option("--ref"))}}
        github["caches"] = [cache for cache in github["caches"] if cache["id"] not in gone]
    case ["cache", "delete"]:
        github["caches"] = [cache for cache in github["caches"] if str(cache["id"]) != args[2]]
    case ["api", *_]:
        path = [arg for arg in args[1:] if not arg.startswith("--")][0]
        base = f"repos/{{github['repository']}}"
        if path == base:
            answer({{"default_branch": "main"}})
        elif path == f"{{base}}/actions/cache/usage":
            answer({{"active_caches_size_in_bytes": sum(c["size"] for c in github["caches"])}})
        elif path == f"{{base}}/branches":
            answer([{{"name": name}} for name in github["branches"]])
        elif path.startswith(f"{{base}}/compare/main..."):
            answer({{"status": github["compare"][path.split("...", 1)[1]]}})
        elif path.startswith(f"{{base}}/pulls/"):
            answer({{"state": github["pulls"][path.rsplit("/", 1)[1]]}})
        else:
            sys.exit(f"no answer for {{path}}")
    case _:
        sys.exit(f"unexpected gh {{args}}")
described.write_text(json.dumps(github))
"""


@dataclass(frozen=True, slots=True)
class Repository:
    """A repository whose default branch is main: its branches, pull requests and caches."""

    branches: list[str] = field(default_factory=lambda: ["main"])
    # How each branch compares with main, as the compare API's status names it.
    compare: dict[str, str] = field(default_factory=dict)
    # Each pull request's state by its number: open or closed.
    pulls: dict[str, str] = field(default_factory=dict)
    caches: list[dict[str, object]] = field(default_factory=list)

    def cache(self, ref: str, key: str, size: int = 0) -> None:
        """Add a cache of ``ref`` under ``key``, newer than every cache before it."""
        self.caches.append({"id": len(self.caches) + 1, "ref": ref, "key": key, "size": size})


def run_script(
    workdir: Path, repository: Repository, script: str, *args: str, ref: str, **env: str
) -> tuple[subprocess.CompletedProcess[str], list[tuple[str, str]]]:
    """Run ``script`` of scripts/ on ``ref`` against ``repository``.

    Return its result and the caches it left, as (ref, key) pairs.
    """
    directory = workdir / "bin"
    directory.mkdir(exist_ok=True)
    (directory / "gh").write_text(GH, encoding="utf-8")
    (directory / "gh").chmod(0o755)
    described = directory / "github.json"
    described.write_text(
        json.dumps({"repository": REPOSITORY, **asdict(repository)}), encoding="utf-8"
    )
    result = subprocess.run(
        [SCRIPTS / script, *args],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{directory}{os.pathsep}{os.environ['PATH']}",
            "GH_REPO": REPOSITORY,
            "GITHUB_REF": ref,
            **env,
        },
    )
    caches = json.loads(described.read_text(encoding="utf-8"))["caches"]
    return result, [(str(cache["ref"]), str(cache["key"])) for cache in caches]
