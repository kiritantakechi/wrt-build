# r4s-build-foundation validation

Validation is fully automated and runs in the emulator; no step needs an R4S. Every foundation spec scenario (archived in `openspec/specs`, the change in `openspec/changes/archive/2026-09-30-r4s-build-foundation`) maps to a test, or is registered in `tests/verified-elsewhere.toml` as verified elsewhere, together with the build or CI job that verifies it. The tool output is authoritative for this mapping, and no separate table is kept here; `just check` fails on any archived scenario without one:

```sh
nix develop .#quality -c uv run --directory tests --locked spec-coverage
```

Run all tests in the emulator against the shipped image of a build (in the local VM or the CI `system-test` job):

```sh
nix develop -c just test dev      # or: just test ci
```

The report is written to `tests/.reports/emulation.xml`.

What the emulator cannot run (the RK3399 boot ROM, the R4S's U-Boot and device tree, the physical ports) is checked statically in the shipped image instead; see design D14.
