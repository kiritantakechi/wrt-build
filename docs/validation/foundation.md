# r4s-build-foundation validation

Validation is fully automated and runs in the emulator; no step needs an R4S. Every foundation spec scenario maps to a test, or is registered in `tests/verified-elsewhere.toml` as verified elsewhere, together with the build or CI job that verifies it. The tool output is authoritative for this mapping, and no separate table is kept here:

```sh
nix develop -c sh -c 'cd tests && uv run spec-coverage --change r4s-build-foundation'
```

Run all tests in the emulator against the shipped image of a build (in the local VM or the CI `system-test` job):

```sh
nix develop -c just test dev      # or: just test ci
```

The report is written to `tests/.reports/emulation.xml`.

What the emulator cannot run (the RK3399 boot ROM, the R4S's U-Boot and device tree, the physical ports) is checked statically in the shipped image instead; see design D14.
