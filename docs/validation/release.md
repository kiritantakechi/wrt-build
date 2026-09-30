# r4s-release-pipeline validation

Validation is automated and needs no R4S. Every scenario of the release pipeline's specs maps to a test, or is registered in `tests/verified-elsewhere.toml` with what verifies it instead (the signing approval, which GitHub's environment protection enforces and `scripts/github-audit.sh` reads back). The tool output is authoritative for this mapping:

```sh
nix develop .#quality -c uv run --directory tests --locked spec-coverage --change r4s-release-pipeline
```

The tests run on the host (the workflows' audits, signing, publishing, the weekly bump) and in the emulator (device sync, the config push, the upgrade drill), in the `release` shard of `system-test`, with release keys made for the run:

```sh
nix develop -c just test dev release ops unit
```

`upgrade-drill` runs the drill tests again after signing, with the production keys, from the latest stable release:

```sh
nix develop -c just drill-base
WRT_SIGNED=<signed build> nix develop -c just test drill-base -m drill
```

## The first release

The first bump followed `docs/release-flow.md` end to end; each step's record:

| Step | Record |
|---|---|
| GitHub settings (`just github-audit`) | |
| Release keys uploaded, `RELEASE_SIGNING` enabled | |
| Bump pull request | |
| Candidate build: signing approved, drill passed | |
| Candidate (pre-release) | |
| Merge, main's build: signing approved, drill passed | |
| Stable release | |
