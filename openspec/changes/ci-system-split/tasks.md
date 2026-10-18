# Tasks

## 1. The suites (design D1, D2)

- [ ] 1.1 Add the `build/ci` test "Every test in one job" to `tests/build/test_ci.py` (D2).

  Verify: it fails against today's matrix only if a module is left out or doubled (today none is); `spec-coverage --change ci-system-split` reports the scenario covered.
- [ ] 1.2 Split the `system` suite into `upgrade`, `boot` and `system` in `build.yml` (D1), and describe the six test jobs in `docs/ci.md`.

  Verify: the partition test passes; `just check` passes.

## 2. Integration (design D3)

- [ ] 2.1 Get a green CI run for both boards with the six suites.

  Verify: record the run in `docs/ci.md`, each test job's time, the longest under 80 min.

## Workflow follow-up

- Sync the delta spec, archive the change, merge it to main and push Codeberg first, then GitHub.
