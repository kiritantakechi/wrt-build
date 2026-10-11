# Tasks

## 1. The toolchain and the target follow the toolchain's inputs (design D1, D2, D3)

- [ ] 1.1 Write the openwrt patch (D1, D2):
  - `.ver_check` as the content hash of `toolchain/` and the target kernel version's generic files, for every build;
  - those generic directories among the inputs of the toolchain's compile stamp;
  - `$(BUILD_DIR)/.toolchain` with its rule before `$(BUILD_DIR)/.prepared`;
  - `check-toolchain-clean.sh` and `toolchain_rebuild_check` removed.

  Carry it under the next free openwrt patch number with `Upstream-Status: Pending`, and its write-up in `docs/patches.md`.

  Verify: `just patch` applies it. On the VM, with the dev profile, a first `just build` builds the toolchain and the board anew, and a second one compiles nothing (time report, compiler cache reports).
- [ ] 1.2 Remove `.ver_check`'s writing from `toolchain-build.sh` (D3), with its comment, and update `docs/dev-setup.md` on when a toolchain and a board are built anew.

  Verify: `just check` passes. `just toolchain-build ci` on a configured tree leaves a `.ver_check` holding the content hash, and a following `just build <board> ci` compiles no toolchain part.
- [ ] 1.3 Verify the build/environment scenario "Change a toolchain patch" on the VM: add a no-op GCC patch to `toolchain/gcc/patches-15.x` through a scratch patch, build both boards, remove it, and build both again.

  Verify: each change rebuilds the toolchain once and compiles every package of each board anew, as the time reports and compiler cache reports show; the record is the scenario's entry in `tests/verified-elsewhere.toml`.

## 2. CI's toolchain key (design D4)

- [ ] 2.1 Add `HEAD:target/linux/generic` to `toolchain-key.sh`, and its mention to `docs/ci.md`'s description of the key and to the verified-elsewhere entries of the build/ci scenarios "Only the packages feed updated" and "Toolchain inputs change".

  Verify: the key changes when a file under `target/linux/generic` changes in a scratch commit, and stays when only the packages feed's SHA changes.

## 3. Main's caches kept whole (design D5, D6)

- [ ] 3.1 Write `scripts/cache-room.sh` and `scripts/cache-prune.sh` with their `just` recipes, and unit tests with a stand-in `gh`:
  - the room check on the default branch and on another ref, with and without room;
  - the pruning of superseded caches;
  - the deletion of merged and deleted branches' caches, and the keeping of unmerged ones.

  Verify: the unit tests pass, and `just check` passes.
- [ ] 3.2 Wire them into `build.yml`:
  - the room check before each compiler or download cache save;
  - `actions: read` for the build jobs;
  - the `caches` job running the prune script from a checkout.

  Document the policy in `docs/ci.md` (jobs table, Cache usage).

  Verify: actionlint passes (`just check`).

## 4. Integration

- [ ] 4.1 Run the full system tests on both boards (dev profile).

  Verify: all tests pass on both boards, and `spec-coverage --change build-integrity` reports no uncovered scenario.
- [ ] 4.2 Get a green CI run for both boards on the branch, with main's caches present.

  Verify: after the run, every cache of main is still listed (`gh cache list`), and the branch's caches fit the quota. Record the run, its per-board timings and the cache listing in `docs/ci.md`, and the build/ci scenario "A branch runs while main's caches fill the quota" in `tests/verified-elsewhere.toml`.

## Workflow follow-up

- Sync the delta specs, archive the change, merge it to main and push Codeberg first, then GitHub.
- After main's run, check that the branch's caches are gone, and record the build/ci scenario "A merged branch" in `tests/verified-elsewhere.toml` and the run in `docs/ci.md`, in the next change or a docs commit.
