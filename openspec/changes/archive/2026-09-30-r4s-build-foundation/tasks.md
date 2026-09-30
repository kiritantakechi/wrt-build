# Tasks

## 1. Repository skeleton and build environment

- [x] 1.1 Create the repository directory structure: `patches/{openwrt,packages,luci}`, `feed/`, `config/`, `files/`, `scripts/`, `docs/`, `.github/workflows/`. Exclude the build directory in `.gitignore`. Verification: `git status` is clean and all directories exist.
- [x] 1.2 Write `flake.nix`: use `buildFHSEnv` to provide the host dependencies OpenWrt needs, `just`, and a pinned clang/llvm (for compiling BPF). Generate `flake.lock`. Verification: in the NixOS VM, `nix flake check` passes and `nix develop -c true` exits with status 0.
- [x] 1.3 Add an `env-report` recipe to the `justfile` that outputs the version list of the host tools. Verification: in 11.3 this list is compared item by item with the CI output.
- [x] 1.4 Create a NixOS VM in OrbStack; create an ext4 image file on the external SSD and loop-mount it in the VM as `WRT_WORKDIR`; document the steps in `docs/dev-setup.md`. Verification: `findmnt $WRT_WORKDIR` shows ext4; creating two files in this directory whose names differ only in case succeeds for both; used space on the macOS system disk does not grow.
- [x] 1.5 Write a host check script that every `just` recipe that fetches or compiles source calls first: on a non-Linux host it exits immediately. Verification: running `just fetch` on macOS returns nonzero with a message and creates no directories.
- [x] 1.6 Add a `nixpkgs-unstable` input to the flake to provide `uv`, `qemu`, `dtc`, `u-boot-tools`; add `shfmt`, `nixfmt`, `actionlint`, `editorconfig-checker`, `gitleaks` to the devShells on both platforms (design D10). Verification: `nix flake check` passes; `just env-report` outputs the versions of uv, qemu, shfmt, nixfmt, actionlint, editorconfig-checker, gitleaks.

## 2. Upstream pinning and patch flow

- [x] 2.1 Define the format of `upstream.lock`: each repository records its URL, SHA, and commit timestamp. The initial values are openwrt `1019293` and the packages and luci SHAs of that time, documented in `docs/upstream-lock.md`. Verification: all three SHAs in the lock resolve to commits in the upstream repositories.
- [x] 2.2 Implement `scripts/fetch.sh` (for `just fetch`): shallow-fetch openwrt by SHA; generate a `feeds.conf` with `^sha`, plus a `src-link` for our own feed; write `version.date`; run `feeds update -a`. Verification: across two runs on different machines or at different times, the SHAs checked out for all three repositories match the lock; `feeds.conf` contains no branch name.
- [x] 2.3 Implement `scripts/patch.sh` (for `just patch`): run `git am` per repository in file name order, with a fixed committer identity and time; on failure, run `--abort` first, then exit and report the patch file name. Verification: with a deliberately conflicting patch, the command returns nonzero and names that file; after removing it and running twice, the resulting source tree HEAD SHAs are identical.
- [x] 2.4 Write a check script (for `just lint`) that scans `scripts/`, the `justfile`, and the workflows for patterns that execute or apply remote downloads, and for `sed -i` on the source tree. Verification: the current repository passes the check; temporarily adding a `curl ... | sh` line makes the check fail.

## 3. Configuration composition

- [x] 3.1 Following design D5, write the seed fragments under `config/`: `target`, `toolchain`, `kernel`, `rootfs`, `system`, `ci`, `dev`. Verification: covered by the verification in 3.2.
- [x] 3.2 Implement `scripts/config.sh` (for `just config <profile>`): concatenate the seeds, run `make defconfig`, check line by line that every seed line is still in `.config`, and finally output the diffconfig artifact. Verification: both the `dev` and `ci` profiles pass; with a deliberately added nonexistent option, verification fails and reports that line.
- [x] 3.3 Make `config.sh` link `config/kernel.config` to `$TREE/env/kernel-config`; after the build completes, `build.sh` verifies the kernel `.config` line by line (design D7). Verification: every line of the overlay appears in the kernel `.config`; with a deliberately added nonexistent symbol in the overlay, `build.sh` fails and reports that line.

## 4. Toolchain and kernel

- [x] 4.1 Provide F2FS compression through the kernel config overlay: write the five F2FS compression options into `config/kernel.config`, remove `KERNEL_F2FS_*` from `kernel.seed`, delete the original patch 0001 (moved to `docs/upstream/`), and renumber the BBRv3 and boot script patches to 0001 and 0002. Verification: in the kernel `.config`, `F2FS_FS_COMPRESSION`, `F2FS_FS_LZ4`, `F2FS_FS_ZSTD` are y, and LZO and LZ4HC are not set; only two patches remain in the queue; two consecutive runs of `just patch` produce the same HEAD.
- [x] 4.2 Write the BBRv3 patch, adding sbwml's 20 patches to `target/linux/generic/hack-6.18/`, keeping patch 0019 as well. Verification: `make target/linux/prepare` applies all patches cleanly; `tcp_bbr.ko` compiles, and its symbol table contains the BBRv3-only `bbr_skb_marked_lost` and `bbr_tso_segs` (OpenWrt's `MODULE_STRIPPED` removes `MODULE_VERSION`, so the version number is not checked).
- [x] 4.3 Add `files/etc/sysctl.d/13-default-qdisc.conf` containing `net.core.default_qdisc=fq`. Verification: covered by the system tests in 10.2.
- [x] 4.4 Check the compiler flags: build one target package with `V=s`. Verification: in the log, `-O2 -mcpu=cortex-a72.cortex-a53+crypto` comes after `-Os`, and the cross compiler's GCC major version is 15.
- [x] 4.5 Do a full build with the `ci` profile. For each package that fails to build with LTO enabled, add a `no-lto` opt-out in `patches/packages` and register it in `docs/lto-optouts.md`. Verification: the full build succeeds (done by the `firmware` job in 11.2), and the packages in the register match the patch queue one to one.
- [x] 4.6 Add the QEMU virt platform drivers (PL011, `PCI_HOST_GENERIC`, virtio-pci/blk/net, i6300esb) to `config/kernel.config`, and use `make listnewconfig` to give explicit values to all newly appearing sub-options. Verification: all these drivers are y in the kernel `.config`; the output of `listnewconfig` is empty; the growth of the `Image` size compared with before is recorded in `docs/kernel.md`.

## 5. Root filesystem and boot

- [x] 5.1 Build with `rootfs.seed`. Verification: `bin/targets/rockchip/armv8/` contains only the erofs sysupgrade image, with no squashfs or ext4 images.
- [x] 5.2 Write the boot script patch that appends `fstools_overlay_compression_type=zstd` to bootargs. Verification: the generated `boot.scr` contains this argument; the mount options of `/overlay` are covered by the system tests in 10.1.

## 6. Base system

- [x] 6.1 Add a `zsh-plugins` package to our own feed that pins autosuggestions and syntax-highlighting to specific tags with hash verification, and provides a global zshrc that loads them. Verification: unpacking the generated apk shows both plugins and the zshrc at the expected paths.
- [x] 6.2 Add `files/etc/profile.d/99-zsh.sh`, which runs `exec zsh -l` only for an interactive login when zsh is executable. Verification: the three shell scenarios are covered by the system tests in 10.3.
- [x] 6.3 Add a uci-defaults script that writes `zram_size_mb=1024` and `zram_comp_algo=zstd` only when the two zram options are unset. Verification: covered by the system tests in 10.3: after a fresh install there is a 1 GiB zstd zram; after changing the value to 512 and doing a config-preserving upgrade, the value is still 512.
- [x] 6.4 Implement the image audit (for `just audit-image`), checking the following: no urngd, nginx, uwsgi, opkg, libpcre (PCRE1), LRNG, shortcut-fe, natflow; no executable with a UPX marker; root has no password hash in `/etc/shadow`; the luci zh-cn language pack is installed. Verification: run against the image produced in 5.1, the audit passes.
- [x] 6.5 Add bash to the image (the default interactive shell is still zsh); the switch script takes effect only for ash logins. Verification: the line-by-line verification of `just config dev` passes; the image audit shows bash installed; the `bash -l` scenario is covered by the system tests in 10.3.

## 7. Code standards

- [x] 7.1 Add `.editorconfig` and `.shellcheckrc` (enabling the optional checks listed in design D12), and fix all warnings in the existing code. Verification: `editorconfig-checker` and `shellcheck` both pass.
- [x] 7.2 Reorder the existing scripts to the common skeleton and format them with shfmt; rename `audit-image` to `image-audit`; add `workdir-unmount`, paired with `workdir-mount`; group the justfile with `[group(...)]`, with recipe names matching script names. Verification: the skeleton check passes; after removing `set -eu` from any script, the skeleton check fails and names that script.
- [x] 7.3 Implement `scripts/check.sh` and `scripts/fmt.sh` (for `just check` and `just fmt`), covering shfmt, shellcheck, nixfmt, ruff format/check, ty, actionlint, editorconfig-checker, gitleaks, the forbidden-pattern checks, and the skeleton check; the former `just lint` is merged into `just check`. Verification: on both macOS and the VM, `just fmt` followed by `just check` passes; `tests/quality/test_code_standards.py` creates one violation for each kind of check in a temporary copy of the repository and confirms that the check fails and points to the location.
- [x] 7.4 Write `docs/conventions.md`, documenting all rules, the script skeleton, and the naming rules. Verification: every rule in the document has a corresponding check in `check.sh`, and vice versa.

## 8. Test framework

- [x] 8.1 Set up `tests/` as a uv project: `pyproject.toml`, `uv.lock`, `.python-version` (3.14); dependencies pytest and labgrid; dev dependencies ruff and ty; each tool's configuration in its own file, `pytest.toml`, `ruff.toml`, `ty.toml`, with rules per design D12. Verification: `uv sync --locked` succeeds; `ruff check`, `ruff format --check`, and `ty check` all pass; after changing a dependency without updating the lock file, `uv sync --locked` fails.
- [x] 8.2 Implement the `@spec` marker, the `spec-coverage` coverage report tool, and `verified-elsewhere.toml`; `spec-coverage` also checks the directory rules (design D13). Verification: the coverage report lists every foundation scenario and its test; marking a nonexistent scenario makes the check fail and names that test; when the capability in `@spec` does not match its module, the check fails.
- [x] 8.3 Write the labgrid target description `targets/emulation.yaml` and `just test`. Verification: `just test` collects the whole suite and runs it against the emulator.
- [x] 8.4 Write `tests/testing/test_harness.py`, covering on the host the automatable scenarios of the testing/harness spec: the coverage report, a marker naming a missing scenario, the lock file out of sync with its declarations, and type errors. The "Test failure" scenario is verified by 11.6 and registered in `verified-elsewhere.toml`. Verification: all tests pass.

## 9. Emulation environment

- [x] 9.1 Implement extraction of the shipped artifacts: decompress the image (tolerating the fwtool trailer), extract `Image` from the FIT and decompress it, generate the boot arguments from `boot.scr` (replacing the serial console and computing PARTUUID from the MBR signature); record the sha256 values and compare them with `manifest.json`. Verification: running the extraction on a locally built image, the sha256 values match the build manifest; the boot arguments contain `fstools_overlay_compression_type=zstd` and the correct `root=PARTUUID`.
- [x] 9.2 Generate the R4S-identity device tree: dump the `virt` device tree with the same arguments used at boot, then rewrite `compatible` and `model` with `fdtput`. Verification: in the emulator, `ubus call system board` shows `friendlyarm,nanopi-r4s`.
- [x] 9.3 Implement the rootless network sandbox: a user namespace, two bridges `br-lan` and `br-wan`, and two network namespaces `client-a` and `isp`; the topology is declared as data in `wrt_tests/net.py`, and later changes only add entries. Verification: running as a regular user, `client-a` gets an address in 10.0.0.0/24 through DHCP and can reach 10.0.0.1. In the OrbStack VM it is confirmed that a regular user can create veth, bridge, and tap devices in a user namespace; CI relies on the AppArmor setting in `prepare-runner.sh`, so no sudo fallback is needed.
- [x] 9.4 Implement fault injection: restore the disk with a qcow2 overlay for each test, force a power cut and reboot from the same disk, provide the i6300esb watchdog, and send keystrokes to the serial console during boot. Verification: `tests/testing/test_emulation.py` covers every scenario of the testing/emulation spec, and all pass.

## 10. System tests (one module per spec capability)

- [x] 10.1 `tests/firmware/test_rootfs.py`: `/rom` is erofs; `/overlay` is f2fs with zstd; factory reset clears only the overlay and leaves EROFS unchanged; the image boots directly. Verification: all pass in the emulator.
- [x] 10.2 `tests/firmware/test_kernel.py`: kernel version, BTF, cgroup2 only, tcx programs load, filesystems need no modules, BBRv3 callbacks and sysctl plus `ss -ti`, virt drivers. Also kmod compatibility tests: a kmod installed from the repository of the same build loads successfully; a virtual package that depends on the running kernel version with a different vermagic, which is exactly the dependency of a kmod from another kernel configuration, is rejected at install time. Verification: all pass in the emulator.
- [x] 10.3 `tests/firmware/test_base_system.py`: LAN address (fresh install, config-preserving upgrade, failsafe mode); LuCI served by uhttpd, with a Chinese-language browser seeing the Simplified Chinese interface; no nginx or uwsgi in the image; the four shell scenarios; zram (covering both cases of 6.3); no preset password; excluded components. Verification: all pass in the emulator.
- [x] 10.4 Change the former manual checklist in `docs/validation/foundation.md` to point to the automated tests, with no manual or device items left. Verification: the `spec-coverage` report shows no uncovered foundation scenarios; build-domain and firmware/toolchain scenarios that a host test cannot check are registered in `verified-elsewhere.toml`, each naming the CI job or command that verifies it.

## 11. CI

- [x] 11.1 Write the `host-toolchain` job: install Nix, prepare the runner, and compute the cache key per design D11; on a cache miss, build the tools and toolchain, pack only the paths that actually exist, and save them. Verification: a cold-cache run finishes within 6 hours, with the duration of each stage recorded in `docs/ci.md`; a second run hits the cache and finishes within minutes.
- [x] 11.2 Write the `firmware` job: refresh file timestamps when restoring the toolchain, and restore the ccache and dl caches; build with the `ci` profile; generate `manifest.json`; upload unsigned artifacts. Verification: the job finishes within 6 hours; the vermagic in the manifest matches the kernel version identifier that the `kmod-*` dependencies in the image refer to.
- [x] 11.3 Check the environment and permissions. Verification: the output of `just env-report` in CI is identical to the local one; the workflows reference no secrets; a run in a fork with no secrets configured succeeds.
- [x] 11.4 Check cache usage. Verification: the total size of the toolchain cache and ccache is recorded in `docs/ci.md`; if it exceeds 10 GB, store the toolchain as a Release asset instead per design D11, and confirm that the next run restores it correctly.
- [x] 11.5 Split the code-standard checks into a separate `check.yml` that runs `just check` on every push, with no path filter. Verification: a docs-only push triggers only `check.yml`, not `build.yml`; pushing a deliberate formatting problem makes `check` fail.
- [x] 11.6 Add a `system-test` job to `build.yml`: it depends on the `firmware` artifacts, runs `just test`, and publishes the JUnit report. Verification: the job finishes within 30 minutes; after deliberately making a test fail, the job fails and the report includes that test.

## 12. Boot chain and upstream contributions

- [x] 12.1 Check in the shipped image the boot chain that the emulator cannot run: the RK3399 loader at sector 64, the R4S U-Boot FIT with TF-A at sector 16384, the boot script, and the R4S device tree in the kernel FIT with both ports enabled (firmware/rootfs, "Inspect the boot chain"). Check that the drivers of both ports register at boot (firmware/kernel, "Port drivers registered"). The other hardware-only items of design D14 belong to later changes: USB UAS to r4s-services, the watchdog to r4s-ab-rollback. Verification: both tests pass in `just test`.
- [x] 12.2 Drop the device target, since no verification step needs an R4S: remove `@target`, `--target-kind`, `targets/r4s.yaml` and `just test-device`, and compile the tcx test program with clang instead of writing its ELF object by hand. Verification: `spec-coverage` shows no uncovered foundation scenario, and `just test` passes in CI.
- [x] 12.3 Prepare two upstream patches in `docs/upstream/`: one for the EROFS compression algorithm choice, and one for the F2FS compression `KERNEL_*` options. They are prepared locally only, and submitting them requires the maintainer's explicit consent. Verification: both patches apply cleanly with `git am` to the upstream commit pinned by the lock; `docs/upstream-contributions.md` records the status of both.
