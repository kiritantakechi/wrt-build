# Tasks

## 1. Spec names in the tests

- [x] 1.1 Point the tests' `@spec` markers at the engine-neutral names: the scenarios renamed in the main specs (transparent-proxy, dns, config-push) and the requirements this change renames (dns, tc-hook-order, config-push).

  Verify: `just check` passes, its spec coverage reading the active change.

## 2. The toolchain (design D2, D3)

- [x] 2.1 Build `crates/honk-ebpf` of the pinned honk release with OpenWrt's host rustc (`RUSTC_BOOTSTRAP=1`, `-Zbuild-std=core`, `bpfel-unknown-none`) and a bpf-linker 0.11.0 built from source against the flake LLVM of rustc's LLVM major (D2).

  Verify: the object has a `.BTF` section and the program sections honk loads (`llvm-objdump -h`), from a clean build on the VM.
- [x] 2.2 Raise OpenWrt's `lang/rust` to the version honk pins if honk's workspace does not build with 1.96.1: a packages patch with its write-up in `docs/patches.md`.

  Verify: honk's workspace builds for aarch64 musl with the tree's Rust; einat builds; the reviewed-warnings register still matches.
- [x] 2.3 Add bpf-linker as a host package from its release source, hash-verified, built with its Cargo.lock against the flake's LLVM (D2).

  Verify: `make package/bpf-linker/host/compile` installs `bpf-linker` under the host staging directory, and 2.1's object builds with it.
- [x] 2.4 Add Node and brotli to `flake.nix`, and doona as a host package of our feed: its source and the pnpm its `packageManager` names, hash-verified, built and packaged as doona's release is (D3).

  Verify: `node --version` in the build environment (`nix develop path:. -c wrt-test-fhs -c 'node --version'`) is within doona's `engines`; `make package/doona/host/compile` installs both editions, each with its notices (`LICENSE`, `NOTICE`, `THIRD-PARTY-NOTICES.txt`), under the host staging directory.

## 3. The honk package (design D1, D3, D5, D6, D8, D10)

- [ ] 3.1 `feed/net/honk/Makefile`: honk's tag archive and doona's source archive, hash-verified; doona built with pnpm (frozen lockfile) and vite; the eBPF object from 2.1's recipe; honk-core with features `ebpf`, `native-ui`, `jemalloc`, `rprx` and the object through the `build.rs` patch (D2), meant for upstream, with its write-up.

  Verify: the package builds for both boards from a clean build directory; the image's `honk-core --version` names the pinned release; the reviewed-warnings register check passes on both boards' `warnings.json`.
- [x] 3.2 The init script with the entry of D4 (the configuration's directory copied as the entry's, root-only; the firmware's settings included last, so they win), procd with respawn and `term_timeout` 30 s, CPU pinning, reload after honk's check (D5); uci `honk` with `config_file` and `cpu_pinning`; the template `/etc/honk/config.dae` with the native API off; the health check (D6); `keep.d` for `/etc/honk`; the service disabled in the image. Remove `feed/net/dae`.

  Verify: the transparent-proxy tests of binding, cgroup programs, health check, CPU pinning, turning off, falling back and the image's template pass on the R4S.
- [x] 3.3 `honk-core -c <file> check`: parse and admit a configuration as a start would, touching nothing, exit nonzero with the reason; a patch meant for upstream with its write-up (D7). The init script checks before it starts or reloads.

  Verify: a unit test of the patch in honk's own test style passes in the package build; on the router, `honk-core check` rejects a configuration routing to a missing group and accepts the test configuration.
- [x] 3.4 Seeds and packages: `config/datapath.seed` (honk, luci-app-honk, `kmod-nft-queue`, `kmod-nfnetlink-queue`), `scripts/image-audit.sh`; honk's marks in `config/marks.tsv` (D9, D10).

  Verify: `just check` (marks check) passes; `scripts/image-audit.sh` passes on the R4S image; the tc-hook-order tests, the NFQUEUE table's survival of `fw4 reload` and its removal after honk stops, and the listener test pass on the R4S.
- [x] 3.5 honk's data directory on the data disk while it is mounted and writable, in RAM otherwise, never on the boot disk; the disk's mount and unmount restart honk onto it and off it (D5). `honk-core check` admits a configuration whose geodata is not there yet, as a start does (D7).

  Verify: the storage/data-disk tests of the proxy's state pass on the R4S; the check's unit test of missing geodata fails without the fix and passes with it.
- [x] 3.6 honk leaves the network-namespace registry `/run/netns` to the other tools that share it: made a mountpoint as iproute2 and podman make it, never unmounted; a patch meant for upstream with its write-up (D7).

  Verify: honk's root-only unit test of the registry fails without the fix and passes with it; the services/containers test of honk's restart beside the Pods fails on the unpatched honk, and it and the storage/data-disk test of the late mount pass on the R4S.

## 4. LAN DNS (design D4)

- [x] 4.1 The dns tests for honk, and the new ones: a LAN client's `.lan` query at the router answered by dnsmasq and not in honk's log, and a container resolving another container's name with honk running.

  Verify: the network/dns tests and the services/containers test of name resolution pass on the R4S.

## 5. honk #456: the router reachable from the LAN (design D7)

- [ ] 5.1 Add the test of "Connect to the router from the LAN" and reproduce the failure on the emulator; pin the mechanism with kprobes and honk's debug log before choosing a fix.

  Verify: the test fails on the unpatched honk, with the mechanism recorded in the patch's write-up.
- [ ] 5.2 Fix it in honk, a patch meant for upstream with its write-up.

  Verify: the test passes on both boards, five runs in a row on the R4S; the transparent-proxy tests still pass.

## 6. honk #476: a reload keeps honk running (design D7)

- [x] 6.1 Make the LuCI-save test require the same honk process after the reload, and reproduce #476 on the emulator; pin the mechanism. The transparent-proxy test of firewall reloads while flows wait for honk's decision (D7: the kernel drops the queued packets, and honk took its answer to their verdicts for a protocol failure).

  Verify: the test fails on the unpatched honk, with the mechanism recorded in the patch's write-up; honk-nfqueue's unit test and root-only kernel test of a verdict for a dropped packet fail without the fix.
- [ ] 6.2 Fix it in honk, a patch meant for upstream with its write-up.

  Verify: the LuCI-save test and the test of firewall reloads while flows wait pass on both boards, ten reloads in a row keeping the process; honk-nfqueue's tests pass.

- [ ] 6.3 honk withstands a stream of new flows waiting for its decision: a batch's armed direct flows activated under one backend acquisition, and a flow armed only with the time left for its activation; a patch meant for upstream with its write-up (D7).

  Verify: honk's unit tests of batched activation and of a flow without time for its activation fail on the unpatched pump and pass with the patch; the transparent-proxy test of a stream of new flows passes on both boards.

## 7. The LuCI pages from daeuniverse's feed (design D1, D8)

- [x] 7.1 Pin daeuniverse/openwrt-packages in `upstream.lock` as `daeuniverse`; `docs/upstream-lock.md`; the build/upstream-pinning and release/upstream-bump tests for four repositories.

  Verify: `just fetch` and `just patch` set up the feed at the pinned commit; the upstream-pinning and upstream-bump tests pass.
- [x] 7.2 `patches/daeuniverse/`: the doona switch writes a token-mode block with a random token shown once, and the "store db" switch goes (D8). Remove `feed/luci/luci-app-dae`.

  Verify: the LuCI-save test passes through luci-app-honk's ACL; the native API tests (token, LAN only, no writes) pass on the R4S.

## 8. config-push and the tools (design D5, D8, D11)

- [x] 8.1 `scripts/config-push.sh` and `device.uc`: `honk/*.dae.enc`, the rejections of the firmware's settings and of the native API's, honk's check in a scratch directory set up as the service runs it, `/etc/honk` written root-only, honk enabled and restarted, its health check. `scripts/config-init.sh` and its skeleton.

  Verify: the ops/config-push tests pass on the R4S, the new native API rejections among them.
- [x] 8.2 The rest that names dae: `wrt-sync`, `wrt-containers`, `files/etc/uci-defaults/91-wrt-datapath`, the release tests' drill configuration, `tests/wrt_tests/services/datapath.py`; `docs/ops.md`, `docs/services.md`, `docs/release-flow.md` with the moving of the private configuration and D11's dialect list.

  Verify: `git grep -i -w dae` finds only honk's own uses (`dae0`, `daens`, the `.dae` format, honk's `so_mark_from_dae`) and the archive; the release and services tests pass on the R4S.

## 9. Supply chain (design D12)

- [x] 9.1 `docs/supply-chain/honk.md`: the boring-sys and quinn forks, the crates, doona's dependencies and bpf-linker's, with conditions and the re-check on upgrade; remove `docs/supply-chain/dae.md`.

  Verify: every pin the document names matches `feed/net/honk/Makefile`, honk's Cargo.lock and doona's lockfile at the pinned versions.

## 10. Integration

- [ ] 10.1 The six suites on the R4S locally, then CI's build and check for both boards.

  Verify: every suite passes on both boards; `just check` passes; the runs are recorded in `docs/ci.md`.

## Workflow follow-up

- Archive the change once CI is green on both boards, and merge.
- Tell the user to move `dae/` to `honk/` in the private repository before the first push to an upgraded router.
