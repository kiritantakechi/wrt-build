# Proposal

## Why

We want our own OpenWrt firmware for the NanoPi R4S (4GB LPDDR4). The reference, sbwml/r4s_build_script, uses official v25.12.5 as its skeleton, but its approach is neither reproducible nor auditable:

- The rockchip and generic targets are replaced with private repositories that require authorization to access.
- All 84 `git clone` calls pull branch HEAD; none is pinned to a commit.
- The build fetches scripts and patches remotely with `curl` 229 times, and modifies upstream text with `sed -i` in 118 places.
- Sub-scripts are invoked as `bash xxx.sh`, so the `-e` in the shebang has no effect and failures are silently swallowed.

Meanwhile, upstream main (2026-09-27, `1019293`) already ships the rockchip 6.18.52 kernel, U-Boot 2026.07, TF-A 2.15, an EROFS root filesystem (fstools already supports placing the overlay after EROFS on a block device), and apk 3.0.5 natively. Our own base therefore needs only a very thin patch layer.

The firmware must track upstream every week, and manual verification on hardware is slow and not repeatable. Verification must be automated, and it must run **the actual shipped image** in the emulator. No step needs the device: what the emulator cannot run is checked statically in the shipped image.

## What Changes

- **Baseline and pinning**
  - Use `openwrt/openwrt` main as the baseline.
  - `upstream.lock` pins the openwrt, packages, and luci repositories to commit SHAs, initially `1019293`.
- **Patches and configuration**
  - Patches live in `patches/<repo>/*.patch` and are applied with `git am`; any failure aborts.
  - The build does not fetch scripts or patches from the network, and does not use `sed` to modify upstream text.
  - Package configuration is composed from the diffconfig fragments `config/*.seed`, and is verified line by line after `make defconfig`.
  - Kernel options that upstream does not expose as `CONFIG_KERNEL_*` all go into the kernel config overlay `config/kernel.config`. This file is linked to `env/kernel-config`, which upstream supports natively, and is verified line by line after the build.
- **Build environment and orchestration**
  - A Nix flake (`buildFHSEnv`) defines the host tools, shared by the local machine and CI. Locally we use an OrbStack NixOS VM, with the build directory on an external SSD.
  - Builds run only on a Linux host: `KERNEL_DEBUG_INFO_BTF` and `tools/dwarves` are unavailable on macOS.
  - The single orchestration entry point is `just` + POSIX sh. Commands and scripts are named with symmetric verbs, for example fetch/patch/config/build/test, mount/unmount, pack/unpack.
- **Toolchain**
  - GCC 15 + LTO + mold + gc-sections.
  - `-O2 -mcpu=cortex-a72.cortex-a53+crypto` is injected through `CONFIG_EXTRA_OPTIMIZATION`, without modifying `include/target.mk`.
- **Kernel**
  - Use the upstream default, 6.18.
  - Enable BTF, `BPF_EVENTS`, `CGROUPS`/`CGROUP_BPF`; use cgroup v2 only.
  - Build EROFS into the kernel; enable F2FS compression with zstd and lz4.
  - Default congestion control is BBRv3 + fq, using sbwml's 6.18 port, with all 20 patches kept.
  - The shipped kernel has built in the few drivers the QEMU `virt` platform needs (PL011 serial, generic PCIe host controller, virtio disk and NIC, i6300esb watchdog), so the same kernel boots in the emulator.
- **Root filesystem**
  - EROFS (`lz4hc,12`); squashfs is no longer produced.
  - The overlay uses f2fs, with compression enabled by adding `fstools_overlay_compression_type=zstd` to the boot arguments.
  - This change produces a single-slot image and keeps the upstream partition layout; A/B belongs to `r4s-ab-rollback`.
- **Base system**
  - LAN address 10.0.0.1; LuCI uses uhttpd + ucode, ships the Simplified Chinese language pack, and follows the browser's interface language.
  - The login shell stays ash; interactive sessions switch to zsh automatically (with the autosuggestions and syntax-highlighting plugins preinstalled); the image also provides bash.
  - zram-swap of 1 GiB with zstd compression; the image has no preset root password.
- **Not adopted**: UPX, LRNG, urngd, shortcut-fe, natflow, PCRE1, the zh-cn translation conversion script, opkg patches, the i915 real-time kernel patch, running LuCI on nginx/uwsgi, and forged vermagic.
- **Automated system tests**
  - The test suite is built on pytest + labgrid, with the Python environment managed and locked by uv, formatting by ruff, and type checking by ty.
  - The suite runs against the emulator; every testable spec scenario maps to one test.
  - The emulator runs the shipped image itself: the kernel is extracted from the image's FIT, the boot arguments come from the image's `boot.scr`, the machine boots with the R4S board identity (`friendlyarm,nanopi-r4s`), and the network is built in an unprivileged user namespace.
  - Nothing is verified by hand on the device: the boot chain the emulator cannot run (loader, U-Boot, boot script, device tree) is checked statically in the shipped image.
- **Code standards**
  - The following checks are all enforced, and CI fails if any fails: shfmt, shellcheck, nixfmt, ruff format/check, ty, actionlint, editorconfig, and forbidden-pattern checks.
  - All scripts use one skeleton; `just check` runs every check and `just fmt` formats everything.
- **CI**
  - Public GitHub repository + GitHub-hosted runners.
  - Four jobs: `check` (code-standard checks), `host-toolchain` (cached by input hash), `firmware` (`ALL_KMODS`), `system-test` (emulator). Each job stays under 6 hours.
  - The release image and the kmod repository must come from the same build.
  - Signing and release belong to `r4s-release-pipeline`.
- **Upstream contributions** (prepared locally only; submitting requires the maintainer's explicit consent):
  - The config symbol name tested at `include/image.mk:110` is misspelled, so the EROFS LZMA branch is never reached. The fix adds a compression algorithm choice that defaults to lz4hc.
  - Add matching `KERNEL_*` switches for each F2FS compression option.

## Capabilities

### New Capabilities

- `build/environment`: a reproducible Linux build environment. The Nix flake keeps the local VM and CI identical, with just as the single entry point.
- `build/upstream-pinning`: upstream sources and feeds pinned to SHAs, plus how the patch queue is applied and how failures are handled.
- `build/ci`: staged CI, caching, full kmod output, and the constraint that "the image and kmods come from the same build".
- `firmware/toolchain`: the target toolchain version and compiler optimization options.
- `firmware/kernel`: the kernel version, required kernel features (BTF, cgroup v2, EROFS, F2FS compression, emulation platform drivers, the R4S port drivers), and BBRv3.
- `firmware/rootfs`: the layout and behavior of the EROFS root filesystem and the f2fs zstd overlay.
- `firmware/base-system`: factory defaults (LAN address, web interface, language, shell, zram, password policy) and the list of components not adopted.
- `testing/harness`: the test suite, the mapping between spec scenarios and tests, and the Python toolchain.
- `testing/emulation`: booting the shipped image in QEMU as an R4S, with a network topology and fault injection.
- `quality/code-standards`: formatting, static checks, the common script skeleton and symmetric naming, and enforcement in CI.

### Modified Capabilities

(None. The project has no existing specs yet.)

## Impact

- **New directories and files**: `flake.nix`, `justfile`, `upstream.lock`, `patches/`, `config/` (including `kernel.config`), `files/`, `feed/`, `tests/` (pyproject, uv.lock, labgrid targets, tests), `.editorconfig`, `.shellcheckrc`, `.github/workflows/`.
- **External dependencies**:
  - An OrbStack NixOS VM and an external SSD. The VM has no KVM, so local QEMU uses TCG pure software emulation.
  - GitHub Actions hosted runners.
  - PyPI (versions pinned and hashes verified through uv.lock).
- **kmod source**: we build our own kernel, so kmods from the official repository cannot be installed; all kmods come from this project's repository.
- **Kernel source patches that need long-term maintenance**: BBRv3 changes the TCP core, and every 6.18.y update may require rebasing it.
- **Shipped kernel changes**: a few virt platform drivers are added, growing it by about 100-300 KB; these drivers are not loaded on the R4S.
- **Patch layer changes**: patch 0001, which added F2FS options to `Config-kernel.in`, is removed in favor of the kernel config overlay. Only two patches remain: BBRv3 and the boot script.
- **Follow-up changes that depend on this change**: `r4s-ab-rollback`, `r4s-ebpf-datapath`, `r4s-services`, `r4s-release-pipeline`. Their verification builds on the test framework and emulation environment defined here.
