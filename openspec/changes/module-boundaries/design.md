# Design

## Context

See proposal.md for why. The facts the approach rests on:

**Shell.**
- Scripts source `scripts/lib.sh` by the path of the script (`$(dirname -- "$0")/lib.sh`). POSIX sh has no way for a sourced file to know its own path, so `REPO_DIR` comes from the script's path too.
- Helpers that compute run in subshells, `( ... )`, so their variables stay theirs. Only `require_workdir` (which sets `TREE`), `use_tests_venv` and `ensure_fhs` change the caller.
- Twelve functions read `TREE`: `ccache_run`, `sccache_run`, `go_cache_entries`, `go_cache_compiled`, `compiler_cache_trim`, `link_tree`, `write_board_table`, `configure_tree`, `compose_seeds`, `time_log`, `time_report`, `toolchain_rust_std`.
- `scripts/check.sh` checks every script against the skeleton, whose third part is the line that sources `lib.sh`.
- The unit tests call helpers through `sh -c '. lib.sh && <function>'`.
- The toolchain's cache key hashes `toolchain-build.sh` and `toolchain-pack.sh`, but not the library functions they call.

**Harness.**
- No runtime import cycle exists today. The cross-layer references are type-only imports, or calls on a router passed in: `pki.trust` and `keys.install_trust` act on the router; `isp`, `oci`, `pki`, `keys` and `ubsan` import device or sandbox types.
- pytest loads the markers through `-p wrt_tests.plugin` (`tests/pytest.toml`), and `tests/services/conftest.py` and `tests/release/conftest.py` hold their suites' fixtures.
- `spec-coverage` already checks the suite's structure: the directory rule, and one marker per test.

## Goals / Non-Goals

**Goals:**
- Every dependency between pieces of the host-side code is visible where it is used, and `just check` holds it.
- A piece can be read, tested and changed with only what it names: a shell module with the modules it loads, a harness module with its layer and the ones below.

**Non-Goals:**
- Device code: `device-modernization` modernizes it.
- CI's workflow structure: its jobs and caches stay as they are.
- New behavior of any test: tests move and read data through models, and assert what they asserted.
- A rewrite of the scripts in another language (decided with the maintainer: they stay POSIX sh).

## Decisions

### D1. Shell modules, loaded by name

```
scripts/lib/
  core.sh       REPO_DIR, die, info, use, require_linux, workdir_tree, ensure_fhs,
                repo_files, use_tests_venv
  boards.sh     BOARDS_DIR, board_ids, board_field, write_board_table
  tree.sh       link_tree, symlink, update_file, kernel_dir, configure_tree,
                missing_config_lines, move_tree
  seeds.sh      profile_seeds, build_name, merge_seeds, compose_seeds
  cache.sh      ccache_run, sccache_run, go_cache_entries, go_cache_compiled,
                compiler_cache_start, compiler_cache_report, compiler_cache_trim,
                trim_unused
  toolchain.sh  toolchain_libc, toolchain_stages, toolchain_rust_std
  timing.sh     time_log, time_report
  warnings.sh   UB_WARNINGS, ub_warnings, image_logs, warnings_harvest, image_warnings
  upstream.sh   LOCK_FILE, lock_field, lock_feeds, fetch_locked, patch_tree, series_commit
```

**Loading.**
- A script loads core by path, then the rest by name:

  ```
  . "$(dirname -- "$0")/lib/core.sh"
  use boards seeds tree
  ```

- `use` sources `scripts/lib/<name>.sh` once per name.
- A module states its own dependencies with `use` at its top, as `seeds.sh` does with `use boards`.

**Placement.** Each function lives with the domain whose facts it knows: `write_board_table` with the boards, `toolchain_stages` with the toolchain, although it reads a time log.

**Alternatives considered:**
- A file per function makes every script load ten files and hides the domains.
- Keeping one library with sections leaves every script depending on everything.

### D2. The tree as an argument

`require_workdir` becomes `workdir_tree`, which checks `WRT_WORKDIR` as before and prints the tree's path. A script holds it in its own variable:

```
tree=$(workdir_tree)
configure_tree "${tree}" "${wanted}"
```

**Every function that read `TREE` takes the tree as its first argument.** The constants derived from the repository's location remain, and only core and the module that owns each of them define them: `REPO_DIR`, `BOARDS_DIR`, `LOCK_FILE` and `UB_WARNINGS`.

`use_tests_venv` and `ensure_fhs` keep changing the caller's environment: that is their purpose, and their names say so.

### D3. awk programs in files

An awk program of more than ten lines becomes a file beside its module: `ub-warnings.awk` and `image-logs.awk` (warnings), and `merge-seeds.awk` (seeds). The function passes its data through `-v` or the environment.

- The unit tests run each program directly, on made-up input.
- shellcheck, which cannot read awk, stops seeing it as a shell string.

Shorter programs stay inline, where they read as part of the function.

### D4. The module check

A check named `modules` in `just check`:
- `lib-check`, a command of the harness's model layer, reads the library's modules and every script.
- It collects the functions each module defines, and the modules each file loads, transitively through each module's own `use`.
- It fails on any call of a library function that the loaded modules do not provide, naming the file and the function.

A call is a library function's name as a word outside comments. Every library function has a distinct name, so a word match is enough.

**Dead functions.** The same reading finds every library function that no script, other module or unit test calls, and the check fails on it, naming the module and the function. A function is called when its name appears as a word outside comments in another function's body, in a script, or in a test under `tests/`.

The skeleton check expects core's line where it expected `lib.sh`'s, and a `use` line after it when the script loads more than core.

**Alternative considered:** shellcheck's `source=` directives. They tell shellcheck where a file is, but nothing fails when a script calls a function from a module it never loads.

### D5. The harness in four layers

```
tests/wrt_tests/
  __init__.py      spec, the one name every test imports from the package root
  model/           markers (+ the markers plugin), boards, specs, coverage, patches,
                   undefined_behavior, data, outputs, image, trees, poll, keys (signing),
                   lib_check
  sandbox/         net, netprobe, isp, internet, pki (the CA), releases, oci
  device/          emu, router, storage, ab, trust, ubsan
  services/        datapath, vpn, app, drill, config
```

**Layers.**
- `model` is the repository and the build's outputs as data, and the harness's own utilities: nothing in it starts a namespace, a process of the sandbox or the emulator.
- `sandbox` is the network around the board: the namespaces, the ISP and the emulated internet with its CA and its servers.
- `device` is the emulator and the router under test.
- `services` is the router online and what runs on it.

**What moves.** Code that acts on the router moves up to `device/trust.py`, where the router trusts the sandbox's CA and the session's release keys:
- `pki.trust` leaves the sandbox;
- `keys.install_trust` leaves the model, and `keys` keeps making the keys and signing.

**tach** checks the layering:
- `tests/tach.toml` declares the four subpackages as modules, each in its layer, ordered `services`, `device`, `sandbox`, `model`;
- a module may import from its own layer and those below, and nothing above;
- type-checking imports count (`ignore_type_checking_imports = false`), because a type names a dependency as much as a call does.

The package root re-exports only `spec`, which every test imports. The tests themselves are no module of tach's: a test may use every layer.

**Unused modules.** `spec-coverage`'s structure check also reads the harness's imports: a harness module that neither another harness module nor a test imports, and that `tests/pyproject.toml` does not name as an entry point, fails it.

**Alternatives considered:**
- import-linter expresses the same contract. tach is the tool chosen with the maintainer; it is maintained (0.35.2, 2026-10-01) and runs from the uv environment like ruff and ty.
- A layer per test domain (network, storage, release) would follow the suites rather than the dependencies: every suite uses the device and the sandbox.

### D6. Fixtures as each layer's plugin

Each layer has a `fixtures.py`, a pytest plugin with the fixtures of its domain:

| Plugin | Fixtures |
|---|---|
| `model.fixtures` | `emulation_dir`, `emulation_source`, `build_output`, `manifest`, `board`, `profile`, `release_keys`, `signed_repo`, `signed_boards`, `upgrade_image` |
| `sandbox.fixtures` | `network`, `isp`, `app_image`, `repository` |
| `device.fixtures` | `emulator`, `harness_key`, `booted_router`, `ubsan_traps`, `router`, `module_router`, `check_module_traps`, `data_disk` |
| `services.fixtures` | `online`, `internet_zone`, `dae`, `trusted_ca`, `app_pod` |

**Composition.**
- pytest resolves fixtures by name, so a plugin uses the fixtures of the layers below without importing them, and the imports keep to the layering.
- `tests/conftest.py` holds `pytest_plugins` with the four plugins and nothing else.
- The markers plugin moves into `model/markers.py`, beside the marker it registers.
- `spec-coverage`'s structure check fails when the root conftest defines a fixture, as it fails on a test without a marker.

### D7. One schema per data file

`model/data.py` is the one way to read a data file:
- `read_json(path, Model)` reads one document;
- `read_toml(path, table, Model)` reads the entries of a TOML table.

Both raise `DataError`, which names the file, the entry (its index, or its key) and the field, from pydantic's error locations.

The models are strict, with `extra="forbid"`:

| File | Model | Module |
|---|---|---|
| `boards/*.json` | `Board` | `boards` (it already is one; it moves onto `read_json`) |
| `tests/verified-elsewhere.toml` | `VerifiedElsewhere` | `coverage` |
| `tests/reviewed-warnings.toml` | `Review` | `undefined_behavior` |
| `out/.../manifest.json` | `Manifest` | `outputs` |
| `out/.../warnings.json` | `Diagnostic` (a list) | `undefined_behavior` |
| `<emulator>/source.json` | `EmulationSource` | `outputs` (emu-prepare writes it through the model as well) |
| `wrt-toolchain.json` | `ToolchainRecord` | `outputs` |
| `release.json`, `<device>-manifest.json` | `Release`, `ReleaseManifest` | `outputs` |

**Who uses them.**
- Every test reads these files through the models, instead of `json.loads` and dictionary keys.
- `emu.manifest_flags` becomes the `Manifest`'s `cflags` and `kernel_cflags`, as lists.
- The shell scripts keep writing the files with jq. The models are their schema, and the system tests read every file a build writes.

### D8. The toolchain key hashes the modules its scripts load

`toolchain-key.sh` hashes `toolchain-build.sh`, `toolchain-pack.sh` and the library modules the two load, which `use` makes explicit. A change to a function of the toolchain's build then changes the key, as a change to the scripts did.

The skeleton change alters the two scripts anyway, so the key changes once with this change either way.

### D9. One order, one naming, nothing left behind

**Order.** Every shell module and harness module reads top-down:
1. what it is for, in its header or docstring;
2. what it depends on: `use` lines, or imports;
3. its constants;
4. its functions, each helper before the first function that calls it, so that a reader meets nothing undefined.

Every script keeps the skeleton of quality/code-standards. The order is stated in `docs/conventions.md`, and the modules are written in it when they are split (task 5.1) and moved (task 3.1).

**Naming.** Operations that come in pairs are named and placed alike: `toolchain-pack` and `toolchain-unpack`, `workdir-mount` and `workdir-unmount`, `read_json` and `read_toml`, `getenv` and `setenv`. A name says what the function returns or does, in the domain's words, as the existing ones mostly do (`board_field`, `compose_seeds`).

**Nothing left behind.** What this change replaces goes in the step that replaces it: `lib.sh`, `require_workdir` and the global `TREE`, the raw reads of the data files. No alias keeps an old name alive. What the dead-code checks find is deleted, after checking that nothing outside the repository (CI's workflow, `justfile`) calls it.

## Risks / Trade-offs

- [Moving 29 modules breaks an import a grep misses] → The module moves come first, in commits of their own. ty and `just check` fail on any import left behind, and the full suite runs on the emulator before the change is done.
- [The dead-code check flags a function only CI's workflow or the justfile calls] → The check reads `.github/workflows/*.yml` and `justfile` as callers too.
- [tach reports what the layering must allow] → Its config is the layering of D5, nothing more. A report means a module in the wrong layer, and is fixed by moving code, never by an exception in `tach.toml`.
- [The toolchain key changes, so CI's next host stage rebuilds] → Once, from its compiler cache: about 71 minutes (docs/ci.md). It is recorded with the change's CI run.
- [A function's new tree argument is missed in a caller] → The module check finds a function a script does not load, not a missing argument. So each function's first line checks its arguments, `[ -d "$1" ] || die ...`, and the unit tests and a full build of both boards exercise every caller.
- [`device-modernization` names an old path: `tests/wrt_tests/keys.py`, whose trust anchors it moves] → Its proposal and tasks point to `model/keys.py` and `device/trust.py` once this change is archived.

## Migration Plan

The order keeps every step green on its own:
1. The schemas and `model/data.py`, while the package is still flat.
2. The layered packages (`git mv`), `device/trust.py`, the imports, `tests/tach.toml` and the tach check.
3. The fixture plugins, and the root conftest that composes them.
4. The shell modules and their awk files, the tree as an argument, the module check, the skeleton check, the toolchain key's inputs.
5. Before and after, the composed seeds, `.config` and each image's package list of both boards are compared, and must be equal. The full suite runs on both boards, and CI runs green.

Rollback means reverting the change's commits: no output, configuration or device changes.
