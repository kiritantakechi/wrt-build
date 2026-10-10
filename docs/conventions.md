# Code standards

Every rule is enforced by `just check`; the `check` workflow in CI runs the same command and fails if it does not pass. `just fmt` does the formatting and maps one-to-one onto the format checks in `just check`. Both commands run on macOS and Linux, with the tools provided by `nix develop .#quality`; on NixOS they automatically run inside `wrt-test-fhs`, because the Python tools that uv installs are generic Linux binaries.

## Rules and checks

The "Check name" column in the table below uses the names that `scripts/check.sh` prints; the two correspond one-to-one.

| Rule | Check name | Formatter |
|---|---|---|
| Shell script format: POSIX dialect, tab indentation, indented case branches (`.editorconfig`) | `shfmt` | `shfmt -w` |
| Shell script static analysis: `shell=sh`, all optional checks except `require-double-brackets` (`.shellcheckrc`) | `shellcheck` | — |
| Nix format | `nixfmt` | `nixfmt` |
| GitHub Actions workflows, including shellcheck of their `run:` blocks | `actionlint` | — |
| All text: UTF-8, LF, final newline, no trailing whitespace, indent style (`.editorconfig`) | `editorconfig-checker` | — |
| No secrets in history or in files about to be committed | `gitleaks` | — |
| Build steps must not execute or apply downloaded content, and must not modify upstream files in place with `sed -i` | `forbidden-patterns` | — |
| Script skeleton, and one-to-one naming between scripts and just recipes | `skeleton` | — |
| Shell library: every script and module loads the modules whose functions it calls, and every library function has a caller | `modules` | — |
| Packet marks of the configuration templates against `config/marks.tsv` | `marks` | — |
| Board descriptions against their schema (`boards/*.json`) | `boards` | — |
| Python format (`tests/`) | `ruff-format` | `ruff format` |
| Python static analysis: `select = ["ALL"]`, with exclusions listed in `tests/ruff.toml` together with their reasons | `ruff-check` | — |
| Python type checking: all rules treated as errors (`tests/ty.toml`) | `ty` | — |
| Test harness layering: no module imports from a layer above its own (`tests/tach.toml`) | `tach` | — |
| Spec-to-test structure: markers point to existing scenarios, one test per scenario, directory rules (design D13) | `spec-coverage` | — |

Files exempt from these rules: `patches/` and `docs/upstream/` (upstream patches are kept verbatim), `.claude/` (tool-generated), and lock files. OpenWrt package `Makefile`s mix tabs and two spaces by upstream convention, so their indent style is not checked.

## Script skeleton

Every script under `scripts/` is organized in this order:

```sh
#!/bin/sh
# <name>: <one-line purpose>.
# Usage: scripts/<name>.sh [args]
# (optional further comment lines)
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"
use <module>...   # the library modules it calls beyond core, if any

<argument parsing>
require_linux; tree=$(workdir_tree); ensure_fhs build "$@"   # only the guards it needs
<main>
```

- `<name>` matches the file name; the second line ends with a period.
- Scripts must be executable. The library modules under `scripts/lib/` are sourced, not executed, and are not executable; their first two lines are `# <module>: ...` and `# Usage: ...`.
- The exit status of a command substitution must not be swallowed (shellcheck's `check-extra-masked-returns`): assign it to a variable first, then use the variable.
- POSIX sh has no local variables. Variable names used inside a function must not clash with the caller's; when isolation is needed, use a subshell.

## Naming

- **Pipeline stages** use a single verb: `fetch`, `patch`, `config`, `build`, `test`, `check`, `fmt`.
- **Operations on a specific object** use "object-verb": `env-report`, `image-audit`, `runner-prepare`, `toolchain-key`, `toolchain-build`, `toolchain-pack`, `toolchain-unpack`, `workdir-mount`, `workdir-unmount`.
- **Paired operations** have symmetric names: `mount`/`unmount`, `pack`/`unpack`, `check`/`fmt`.
- **Every script has a just recipe of the same name**, and conversely every just recipe (except `default`) has a script of the same name; `skeleton` checks this. Just recipes are grouped into `build`, `image`, `test`, `quality`, `ci` and `workdir`.
- **Environment variables** all use the `WRT_` prefix.

## Shell library modules

The scripts' shared functions live in `scripts/lib/`, one module per domain. A script loads core by its path and the other modules it calls by name, on one `use` line after core's; a module loads what it depends on with a `use` line of its own, and `use` loads each module once.

| Module | Domain |
|---|---|
| `core` | The repository's place (`REPO_DIR`), messages (`die`, `info`), `use` and `loaded_modules`, the host and environment guards (`require_linux`, `ensure_fhs`), the build tree (`workdir_tree`), the repository's files, the tests' virtual environment |
| `boards` | The board descriptions (`BOARDS_DIR`, `board_ids`, `board_field`) and the table of them the A/B hooks read |
| `tree` | The build tree's files: links into it, files written only when they change, its configuration, and moving its checkout |
| `seeds` | A configuration composed from a profile's and a board's seeds |
| `cache` | The compiler caches the tree links to: running them, their statistics and their trimming |
| `toolchain` | What a toolchain was built with, and the stages of a build that built any of it |
| `timing` | A build's time log, and the report of where its time went |
| `warnings` | The UB-indicative warnings (`UB_WARNINGS`): read from a build's logs, recorded, and gathered for an image |
| `upstream` | The sources pinned in `upstream.lock` (`LOCK_FILE`), fetched and patched |

- **The tree is an argument.** `workdir_tree` checks `WRT_WORKDIR` and prints the tree's path; a script keeps it in its own variable, `tree=$(workdir_tree)`, and every function that works on a tree takes it first and checks it. The only globals are core's and each module's constants, derived from the repository's place.
- **A module starts from core**, and says so: `: "${REPO_DIR:?load scripts/lib/core.sh first}"` after its header, before its `use` line.
- **An awk program of more than ten lines** is a file beside its module (`ub-warnings.awk`, `image-logs.awk`, `merge-seeds.awk`), which the function runs with `awk -f` and the unit tests run directly; a shorter one stays inline.
- **`modules`** (`lib-check`) fails on a call of a library function that the modules a file loads do not provide, and on a function that no script, module, test, workflow or recipe calls. The toolchain's cache key hashes the modules its scripts load.

## Test harness layers

The test harness, `tests/wrt_tests`, is four packages, layered from the bottom up. A module imports only from its own layer and the layers below it, type-checking imports included; `tach` checks it with `tests/tach.toml`, which declares the layers and nothing more. A report means a module in the wrong layer, and is fixed by moving code, never by an exception in `tach.toml`.

| Layer | Holds | A new module goes here when it |
|---|---|---|
| `model` | The repository and the build's and the release's outputs as data, and the harness's own utilities: the markers, the board descriptions, the specs and their coverage, the patches, the data files' schemas (`data`, `outputs`), the release keys | starts no process of the sandbox and no emulator, and touches no router |
| `sandbox` | The network around the board: the namespaces, the ISP, the emulated internet with its CA and servers, the Releases stand-in, the test app image | builds or runs the board's surroundings |
| `device` | The emulator and the router under test: its disks and slots, the traps of a ubsan build, its trust in the session's CA and keys | acts on the emulator or the router |
| `services` | The router online and what runs on it: the datapath, the VPNs, the app, the upgrade drill, the pushed configuration | needs the router online |

The package root exports `spec` alone, which every test imports. The tests themselves are no layer's: a test may use every layer. Code that acts on the router belongs to `device` even when the data it puts there comes from below, as `device/trust.py` puts the sandbox's CA and the release keys on the router.

## Order and naming in a module

Every shell library module and every harness module reads top-down, in this order:

1. what it is for: its header comment, or its docstring;
2. what it depends on: its `use` line, or its imports;
3. its constants;
4. its functions, each helper before the first function that calls it, so that a reader meets nothing undefined.

Operations that come in pairs are named and placed alike: `toolchain-pack` and `toolchain-unpack`, `workdir-mount` and `workdir-unmount`, `read_json` and `write_json`, `trust_ca` and `trust_keys`. A name says what a function returns or does, in its domain's words. What a change replaces goes in the same change, without an alias for the old name.
