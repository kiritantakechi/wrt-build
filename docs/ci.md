# CI

There are two workflows, both on GitHub-hosted ubuntu-24.04 runners (4-core x86_64, 6 hours max per job):

| Workflow | Job | What it does | Cache |
|---|---|---|---|
| `check.yml` | `check` | `nix develop .#quality -c just check`; runs on every push, with no path filter | — |
| `build.yml` | `host-toolchain` | Fetch and patch, then build the tools and the cross toolchain | `staging_dir/{host,hostpkg,toolchain-*}` and `build_dir/host`, keyed by `scripts/toolchain-key.sh` |
| `build.yml` | `firmware` | Restore the toolchain, then build with the ci profile (all kmods); produces unsigned artifacts and `manifest.json` | `dl/` and ccache |
| `build.yml` | `system-test` | Download the firmware artifacts; `just test ci` runs all tests in the emulator, then `spec-coverage` checks coverage; uploads the JUnit report | — |

`build.yml` runs only when code changes (changes to `openspec/`, `docs/` and Markdown files do not trigger it), and a new push to the same branch cancels the older pipeline that is still running.

The toolchain cache key depends only on these inputs: the runner architecture, the tree SHAs of openwrt's `tools/` and `toolchain/` directories, the tree SHAs of the packages feed's `lang/golang` and `lang/rust` directories, `config/toolchain.seed`, and the build environment fingerprint `WRT_BUILD_INPUTS` (the store paths of the build packages plus the build profile; see `buildInputsId` in `flake.nix`). So changing only the packages or luci SHA, or adding tools to the test environment, still hits the toolchain cache.

The workflows reference no secrets, and the repository has none configured, so every run is also the run of a fork without secrets. `just env-report` prints the same 28 lines in CI (x86_64) and in the local VM (aarch64), checked on run 36388876907.

## Timings

| Date | Run | Stage | Duration | Notes |
|---|---|---|---|---|
| 2026-09-28 | early trial run | tools (cold cache) | about 43 min | |
| 2026-09-28 | early trial run | cross toolchain GCC 15.3.0 (cold cache) | about 35 min | |
| 2026-09-28 | 36371318405 | host-toolchain job total | 83 min | Building the tools and the toolchain: 79 min 49 s; packing and saving the cache: 6 s |
| 2026-09-28 | 36371318405 | firmware job total | 103 min | Build: 98 min 04 s (empty ccache, empty dl cache, all kmods) |
| 2026-09-28 | 36388876907 | host-toolchain job total | 81 min | New key scheme (`toolchain-v2`), so a cold rebuild: tools and toolchain 77 min 01 s |
| 2026-09-28 | 36388876907 | firmware job total | 138 min | Build: 131 min 45 s; ccache from the previous run, but the kernel configuration changed, so every kmod was rebuilt |
| 2026-09-28 | 36388876907 | system-test job total | 13 min | Tests: 10 min 32 s (64 tests under TCG on x86_64); failed only because `ping` was missing from the test environment |

The first full pipeline on a cold cache took about 3 hours 6 minutes; both build jobs are well within the 6-hour limit.

## Cache usage

The total cache quota for a GitHub repository is 10 GB.

| Date | Toolchain archive | ccache | dl | Nix installer | Total |
|---|---|---|---|---|---|
| 2026-09-28 | 776 MiB | 1243 MiB | 1456 MiB | 45 MiB | 3521 MiB |

Each run saves a new ccache (its key includes the run ID); GitHub evicts old ones least recently used first. At current usage the toolchain can stay in the cache, and there is no need to store it as a Release asset instead (the fallback in design D11).
