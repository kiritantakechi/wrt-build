# Tasks

## 1. Baseline

- [x] 1.1 Record, from the state `toolchain-o3` merged, what the change must leave alone, for both boards, in `$WRT_WORKDIR/module-boundaries-baseline/` (outside the repository):
  - the composed seeds of the dev and ci profiles (`out/<board>/seed-<profile>.config`) and the board-neutral composition (`compose_seeds <profile> ""`);
  - the `.config` that `just config <board> dev` leaves;
  - each image's package list (`targets/*.manifest`).

  Verify: the files exist, two boards by two profiles, and their list is noted for task 6.1.

## 2. One schema per data file (design D7)

- [x] 2.1 Add `wrt_tests/data.py` (still in the flat package): `read_json(path, Model)`, `read_toml(path, table, Model)`, and `DataError`, which names the file, the entry and the field.

  Verify: unit tests (`tests/unit/test_data.py`) for an unknown field, a value of the wrong type and a missing field, each naming file, entry and field, for both readers.
- [x] 2.2 Add the models of D7: `Manifest`, `EmulationSource`, `ToolchainRecord` and `Release` (`wrt_tests/outputs.py`), and `VerifiedElsewhere` (`coverage`). Move `Board`, `Review` and `Diagnostic` onto the readers. emu-prepare writes `source.json` through `EmulationSource` and `write_json`, `emu.manifest_flags` becomes `Manifest.cflags` and `Manifest.kernel_cflags`, and the drill base's manifest becomes a `Manifest`.

  Verify: `git grep -n 'json.loads\|tomllib' tests` finds no read of these files left, only of router output and HTTP bodies. Each model reads a real file of a build or a release in the unit tests' fixtures.
- [x] 2.3 Add the test of the testing/harness scenario "Malformed data file" (`tests/testing/test_harness.py`): for each file of D7, a copy with an unknown field and a copy with a wrong type fail to read, naming the file, the entry and the field.

  Verify: the test passes; with `extra="forbid"` taken off one model, it fails and names that file.

## 3. The harness in layers (design D5)

- [x] 3.1 Move the modules into `model/`, `sandbox/`, `device/` and `services/` with `git mv`, as D5 lays out:
  - split `keys` into signing (`model/keys.py`) and `install_trust`, and `pki` into the CA (`sandbox/pki.py`) and `trust`; both of these go to `device/trust.py`;
  - the package root re-exports only `spec`, and `plugin.py` joins `model/markers.py`;
  - update every import (tests, conftests), the entry points (`board-check`, `emu-prepare`, `spec-coverage`) and `tests/pytest.toml`'s `-p`.

  Verify: `just check` passes, the unit tests pass, and `pytest --collect-only -q` collects the same tests as before the move.
- [x] 3.2 Add tach to the dev dependencies (`tests/pyproject.toml`, `uv.lock`) and `tests/tach.toml` with the four layers. `just check` runs it as the check `tach`. Add the test of the quality/code-standards scenario "Harness module imports from a higher layer" (`tests/quality/test_code_standards.py`), on a scratch copy of the repository with a model module that imports from the device layer.

  Verify: `just check` passes on the tree; the test passes, and its failure output names the module and the import.
- [x] 3.3 Describe the layers in `docs/conventions.md`: what each holds, what it may import, and where a new module goes; and the order and naming of D9, which every moved module follows.

  Verify: the document names the four layers, tach's config and D9's order, and `just check` (editorconfig, links) passes.
- [x] 3.4 Extend `spec-coverage`'s structure check with D5's unused modules, and add the test of the quality/code-standards scenario "Harness module that nothing imports" (`tests/quality/test_code_standards.py`). Delete the harness modules and functions it finds unused.

  Verify: the test passes and names the module; the check passes on the tree.

## 4. Fixtures by layer (design D6)

- [ ] 4.1 Move the root conftest's fixtures into each layer's `fixtures.py`, as D6's table lays out. The root `tests/conftest.py` holds only `pytest_plugins`.

  Verify: `pytest --fixtures` lists the same fixtures as before, the collection is unchanged, and a system test module of each layer (`firmware/test_kernel.py`, `network/test_nat.py`, `storage/test_data_disk.py`, `release/test_publishing.py`) passes on a board's build.
- [ ] 4.2 Extend `spec-coverage`'s structure check: the root conftest defines no fixture. Add the test of the testing/harness scenario "Fixture defined in the root configuration" (`tests/testing/test_harness.py`).

  Verify: the test passes, and the check's output names the fixture.

## 5. Shell modules (design D1–D4, D8)

- [ ] 5.1 Split `scripts/lib.sh` into `scripts/lib/*.sh` as D1 lays out, each module in D9's order, with `use` in core and each module's dependencies at its top. Every script loads core by path and its other modules with one `use` line. The unit tests (`test_lib.py`, `test_warnings.py`) load the modules they test by name.

  Verify: shellcheck and shfmt pass, the unit tests pass, and `scripts/lib.sh` is gone.
- [ ] 5.2 Move the awk programs of more than ten lines into files beside their modules (D3): `ub-warnings.awk`, `image-logs.awk`, `merge-seeds.awk`.

  Verify: the unit tests run each program directly and pass.
- [ ] 5.3 Pass the tree as an argument (D2): `workdir_tree` replaces `require_workdir`, and the twelve functions that read `TREE` take the tree first and check it.

  Verify: `git grep -n 'TREE' scripts` finds no global `TREE`. The unit tests of those functions pass the tree. In the VM, `just config r4s dev` and `just toolchain-build dev` run as before.
- [ ] 5.4 Add `lib-check` (model layer) and the check `modules` to `just check` (D4), with dead functions. Update the skeleton check to core's line and the `use` line. Add the tests of the quality/code-standards scenarios "Script calls a function it does not load" and "Library function that nothing calls" (`tests/quality/test_code_standards.py`), and keep the test of "New script added" passing against the new skeleton. Delete the library functions the check finds dead.

  Verify: the three tests pass, and the check passes on the tree.
- [ ] 5.5 Make `toolchain-key.sh` hash the modules that `toolchain-build.sh` and `toolchain-pack.sh` load (D8), and update the toolchain key's entry in `tests/verified-elsewhere.toml`.

  Verify: in the VM, the key changes when `seeds.sh` changes, and not when `warnings.sh` does.
- [ ] 5.6 Describe the shell modules in `docs/conventions.md`: the modules and their domains, `use`, the tree as an argument, where an awk program goes, and D9's order in a module.

  Verify: the document lists every module of `scripts/lib/`.

## 6. Integration

- [ ] 6.0 Leave nothing behind (D9): `git grep` finds no `lib.sh`, `require_workdir`, global `TREE`, or `json.loads`/`tomllib` read of a data file of D7 in the repository, outside the archived changes.

  Verify: the grep finds nothing, and the dead-code checks of tasks 3.4 and 5.4 pass.

- [ ] 6.1 Build both boards (`just build r4s dev`, `just build r6s dev`), and compose the ci profile's seeds. Compare them with the baseline of task 1.1.

  Verify: the composed seeds, `.config` and each image's package list equal the baseline.
- [ ] 6.2 Run the full system tests on both boards.

  Verify: `just test r4s dev` and `just test r6s dev` pass, and `spec-coverage --change module-boundaries` reports no uncovered scenario.
- [x] 6.3 Point `device-modernization`'s proposal and tasks to the new paths of the trust anchors' code (`model/keys.py`, `device/trust.py`).

  Verify: `git grep -n 'wrt_tests/keys.py' openspec/changes/device-modernization` finds nothing.
- [ ] 6.4 Get a green CI run for both boards.

  Verify: its host stage rebuilt once under the new toolchain key, from its compiler cache. Record the run in `docs/ci.md`.
