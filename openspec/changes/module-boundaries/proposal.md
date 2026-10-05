# Proposal

## Why

The host-side code grew by accretion, change after change, and its parts now depend on each other more than their tasks require:
- `scripts/lib.sh` holds 43 functions of nine domains, from compiler caches to seed composition and UB warnings. Every script sources all of it, and most use two to five. A third of the functions read a global, `TREE`, that `require_workdir` sets as a side effect. The UB-warning parser, a 50-line awk program, sits inline in a shell string.
- `tests/wrt_tests` is one flat package of 29 modules. Pure data models, the sandbox network, the emulated router and the services mix freely, and nothing keeps a lower piece from reaching up: the sandbox's CA module installs its certificate on the router, and the release-key module does the same with the keys.
- `tests/conftest.py` composes every domain in one file: the build under test, the network and the ISP, the emulator and the router, the data disk, the app image, signed releases and UBSan's traps.
- The data the tests read has no single shape. The build's manifest is parsed with `json.loads` in eight places, each picking the keys it needs. `verified-elsewhere.toml` is read as raw dicts, `reviewed-warnings.toml` through pydantic, and the board descriptions through pydantic again with their own error format.

Each new change pays for this: it reads more than it touches, and a mistake in one part surfaces in another. It comes now, between `toolchain-o3` and `device-modernization`, so that the latter's new scripts and tests land in the new structure instead of being moved twice.

## What Changes

- **Shell library modules**:
  - `scripts/lib.sh` becomes modules by domain under `scripts/lib/`: core, boards, tree, seeds, cache, toolchain, timing, warnings and upstream. Each module loads the modules it depends on.
  - A script loads only the modules it uses, by name.
  - Functions take the build tree as an argument instead of reading `TREE`. The remaining globals are constants derived from the repository's location.
  - awk programs of more than a few lines move to files beside their module, where unit tests reach them directly.
  - `just check` fails when a script calls a library function that the modules it loads do not provide.
- **Layered test harness**:
  - `tests/wrt_tests` becomes four subpackages, from the bottom up:
    - `model`: the repository and the build's outputs as data, and the harness's own utilities;
    - `sandbox`: the network, the ISP and the emulated internet;
    - `device`: the emulator and the router;
    - `services`: the router online and what runs on it.
  - A module imports only from its own layer and the ones below it, type-only imports included.
  - tach checks the layering in `just check`.
  - Code that acts on the router moves up to the device layer: installing the sandbox CA and the release keys.
- **Fixtures by layer**:
  - Each layer provides its fixtures as a pytest plugin.
  - The root `conftest.py` only composes the plugins and defines no fixture of its own, which the harness check enforces.
  - The suites' own conftests (services, release) stay where they are.
- **One schema per data file**:
  - Every data file the tests read is read through one pydantic model, strict about unknown fields and types:
    - the board descriptions;
    - the two registers (`verified-elsewhere.toml`, `reviewed-warnings.toml`);
    - the build's manifest, its warnings report and the emulator's source record;
    - the toolchain's record;
    - a release's `release.json` and per-device manifest.
  - Loading fails with the file, the entry and the field.
  - The tests read typed fields instead of dictionary keys.
- **No dead code, and nothing left behind**:
  - the module check also fails on a library function that no script, module or test calls, and the harness check on a harness module that nothing imports;
  - what the change replaces goes in the same step, without an alias for the old name: `lib.sh`, `require_workdir` and `TREE`, the raw reads of the data files;
  - functions and modules found unused are deleted, not kept for later.
- **One order and one naming**:
  - every shell module and harness module reads top-down in the same order: what it is for, what it depends on, its constants, then its functions, each helper before its first caller;
  - operations that come in pairs are named and placed alike, as `toolchain-pack` and `toolchain-unpack`, or `read_json` and `read_toml`, are;
  - `docs/conventions.md` states both.
- **No behavior of the firmware or of the build changes.** The composed seeds, the configuration and the packages of each image stay the same; only the code that builds and tests them moves.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `quality/code-standards`:
  - the script skeleton loads library modules by name, instead of sourcing one library;
  - three new requirements, all checked by `just check`: scripts load what they call; the test harness is layered, each module importing only from its own layer and below; and the host-side code has no dead code.
- `testing/harness`, two new requirements:
  - fixtures by layer, with a root configuration that only composes them;
  - one schema per data file, whose violations name the file, the entry and the field.

## Impact

- **Scripts**:
  - `scripts/lib.sh` is replaced by `scripts/lib/*.sh` and its awk files;
  - every script in `scripts/` loads its modules by name;
  - `scripts/check.sh` gains the module check and tach.
- **Tests**:
  - `tests/wrt_tests/` is reorganized into `model/`, `sandbox/`, `device/` and `services/`, each with its `fixtures.py`;
  - `tests/conftest.py` composes them;
  - `tests/tach.toml` is new, and tach joins the dev dependencies (`tests/pyproject.toml`, `uv.lock`);
  - every test's imports follow the new paths, and its data reads go through the models;
  - `tests/unit/` gains the tests of the module check, of the awk programs and of the schemas;
  - what the dead-code checks find is deleted.
- **Docs**: `docs/conventions.md` describes the shell modules, the harness's layers, and the order and naming every module follows.
- **Unchanged**: the composed seeds, the configuration and each image's packages, which the same comparison before and after the change shows. CI's workflow stays as it is; its check job runs tach through `just check`.
- **Order**: the third of four changes, after the archived `board-model`: `build-acceleration`, then `toolchain-o3`, then `module-boundaries`, then `device-modernization`. `device-modernization`'s new scripts and tests land in its structure.
