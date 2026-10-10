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
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

<argument parsing>
require_linux; require_workdir; ensure_fhs build "$@"   # only the guards it needs
<main>
```

- `<name>` matches the file name; the second line ends with a period.
- Scripts must be executable. `lib.sh` is a sourced library and is not executable; its first two lines are `# lib: ...` and `# Usage: ...`.
- The exit status of a command substitution must not be swallowed (shellcheck's `check-extra-masked-returns`): assign it to a variable first, then use the variable.
- POSIX sh has no local variables. Variable names used inside a function must not clash with the caller's; when isolation is needed, use a subshell.

## Naming

- **Pipeline stages** use a single verb: `fetch`, `patch`, `config`, `build`, `test`, `check`, `fmt`.
- **Operations on a specific object** use "object-verb": `env-report`, `image-audit`, `runner-prepare`, `toolchain-key`, `toolchain-build`, `toolchain-pack`, `toolchain-unpack`, `workdir-mount`, `workdir-unmount`.
- **Paired operations** have symmetric names: `mount`/`unmount`, `pack`/`unpack`, `check`/`fmt`.
- **Every script has a just recipe of the same name**, and conversely every just recipe (except `default`) has a script of the same name; `skeleton` checks this. Just recipes are grouped into `build`, `image`, `test`, `quality`, `ci` and `workdir`.
- **Environment variables** all use the `WRT_` prefix.

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
