# Tasks

## 1. The tests (design D9)

- [x] 1.1 Add the static tests of the workflows and the tests of the scripts against stand-ins (D9).

  Verify: `just check` passes; `spec-coverage --change release-integrity` reports every scenario covered.

## 2. Publishing and signing (design D1, D2, D3)

- [x] 2.1 The manifest's commit, the publish checks and `--target`, build's concurrency (D1).

  Verify: the release/publishing tests pass.
- [x] 2.2 The sign job's boards, `release-sign.sh`'s paths and copies, `--strict` everywhere (D2).

  Verify: the release/signing tests pass.
- [x] 2.3 The local Nix action, used by every job (D3).

  Verify: the workflow tests pass; actionlint passes.

## 3. The merge gate and the bump (design D4, D5)

- [x] 3.1 `upgrade-drill` for a bump's pull request (D4); the bump's order and branch, and `github-audit.sh`'s read-back (D5).

  Verify: the workflow tests and `tests/unit/test_github_audit.py` pass.

## 4. Caches and triggers (design D6, D7)

- [x] 4.1 The download step and its cache, the savers, the pruning of stages and pull requests, the toolchain key's kernel versions (D6).

  Verify: `tests/unit/test_ci_caches.py` passes; the key's behaviour on the VM recorded.
- [x] 4.2 The paths filter and check's concurrency group (D7).

  Verify: the workflow tests pass.

## 5. Host scripts (design D8)

- [x] 5.1 The `justfile`, the series commit's and checkout's git configuration, the UBSan `nm`, `marks-check`, `toolchain-pack` (D8); `docs/ci.md`, `docs/release-flow.md` where they describe these.

  Verify: `just check` passes; the build/upstream-pinning and build/environment tests pass.
- [x] 5.2 `build.sh` removes the packages the configuration does not build before `make`; `warnings_harvest` records the packages the time log names as compiled, a host build's stages named apart (patch 0042) (D8); `docs/undefined-behavior.md`, `docs/ci.md` and `docs/patches.md` where they describe these.

  Verify: `just check` passes; on both boards, an incremental build over earlier ones passes the build/ci "Complete manifest", release/publishing "Inspect Release contents" and quality/undefined-behavior tests.

## 6. Integration

- [ ] 6.1 Get a green CI run for both boards with the change.

  Verify: record the run in `docs/ci.md`.

## Workflow follow-up

- Sync the delta specs, archive the change, merge it to main and push Codeberg first, then GitHub.
