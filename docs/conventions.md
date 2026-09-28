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
| Python format (`tests/`) | `ruff-format` | `ruff format` |
| Python static analysis: `select = ["ALL"]`, with exclusions listed in `tests/ruff.toml` together with their reasons | `ruff-check` | — |
| Python type checking: all rules treated as errors (`tests/ty.toml`) | `ty` | — |
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
