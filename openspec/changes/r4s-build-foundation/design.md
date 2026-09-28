# Design

## Context

See the Why section of proposal.md for motivation. This design depends on the following facts and constraints.

### Upstream (main `1019293`, 2026-09-27, all verified in the source)

- The rockchip default kernel is 6.18.52; U-Boot 2026.07, TF-A 2.15.0, erofs-utils 1.9.4, apk 3.0.5, musl 1.2.6.
- GCC defaults to 14, with 15 optional; llvm-bpf 22.1.3, dwarves 1.31.
- `friendlyarm_nanopi-r4s` is the "4GB LPDDR4" model (`target/linux/rockchip/image/armv8.mk:139-145`).
- The last layer of `LINUX_KCONFIG_LIST` is `$(TOPDIR)/env/kernel-config` (`include/target.mk:173`). This is the kernel config overlay upstream supports natively, and `/env` is already in upstream's `.gitignore`.
- `CONFIG_KERNEL_*` in `.config` is written only into kernel config symbols that are defined in Kconfig (`include/kernel-defaults.mk:118-119`).
- When the kernel config meets a new symbol with no value, the build stops with an error. This already happened when enabling F2FS compression; use `make listnewconfig` to find all symbols missing values in one pass.
- OpenWrt enables `CONFIG_MODULE_STRIPPED`, which removes `MODULE_VERSION` and similar information from modules.

### Host and Nix environment (verified during implementation)

- **Host**: M1 Max, 32 GB memory; an OrbStack NixOS 25.11 VM (aarch64, 9 cores, 15 GB) with no `/dev/kvm`.
- **External SSD**: HFS+, measured sequential write about 75 MB/s.
- **Builds must run on Linux**: `KERNEL_DEBUG_INFO_BTF` and mold both depend on `!HOST_OS_MACOS`, and dwarves is skipped on Darwin.
- **Three things the FHS environment must add**:
  1. `/usr/include` must contain the glibc headers, otherwise CMake's `find_path` cannot find `iconv.h`.
  2. It needs the LTO-capable archiver `gcc-ar`; the host apk requires it when linking static libraries with `b_lto`.
  3. It must set `FAKEROOTDONTTRYCHOWN=1`: in a user namespace, a real `chown` returns EINVAL, while fakeroot only ignores EPERM, so it errors out.
- **Ubuntu 24.04 runners** restrict unprivileged user namespaces with AppArmor; bubblewrap needs this restriction lifted first.

### GitHub-hosted runners

- A single job runs at most 6 hours; the standard Linux runner has 4 cores and 16 GB; the cache totals 10 GB.
- Measured on a cold cache: tools about 43 minutes, the GCC 15 toolchain about 35 minutes.

## Goals / Non-Goals

**Goals:**
- From the same lock, the local machine and CI get exactly the same source tree, configuration, and build timestamp.
- Produce a single-slot SD image and a full kmod repository from the same build.
- Verify as many spec scenarios as possible automatically against the shipped image in the emulator; the device is left with one command plus a few hardware-specific checks.
- Code standards are machine-checkable and enforced in CI.

**Non-Goals:**
- Not in this change: A/B (`r4s-ab-rollback`), datapath (`r4s-ebpf-datapath`), services (`r4s-services`), signing and release (`r4s-release-pipeline`).
- Do not tune the kernel itself with `-mcpu`, and do not cover hardware offload.
- Do not measure performance in the emulator. Throughput measured under TCG is meaningless.

## Decisions

### D1. Repository layout

```
wrt-build/
  flake.nix  flake.lock           host environment (build FHS + tooling)
  justfile                        entry points, grouped: build / image / test / quality / ci / workdir
  upstream.lock                   openwrt / packages / luci: url, sha, commit epoch
  patches/<repo>/*.patch          git format-patch series, applied with git am
  feed/                           own packages (src-link)
  config/*.seed                   package/diffconfig fragments
  config/kernel.config            kernel symbols not exposed as CONFIG_KERNEL_*
  config/profiles                 profile -> seed list
  files/                          rootfs overlay
  scripts/*.sh                    POSIX sh, one skeleton (D12)
  tests/                          pytest + labgrid project (uv), see D13
  .editorconfig .shellcheckrc     style configuration
  .github/workflows/{check,build}.yml
  docs/

$WRT_WORKDIR/  (outside repo)     openwrt/  dl/  ccache/  out/<profile>/  emu/
```

### D2. Fetch upstream by SHA

- **Approach**: openwrt is fetched with `git fetch --depth 1 origin <sha>`. `fetch.sh` also shallow-fetches each feed by SHA itself.
- **Why not let `scripts/feeds update` fetch the feeds**: when a feed directory already exists and carries `^sha`, it skips it, so a changed SHA in the lock would not be picked up. After fetching, we therefore only run `feeds update -i` to rebuild the index.
- **`feeds.conf`**: each feed is written as `src-git <name> <url>^<sha>`, plus one `src-link` line for our own feed.

### D3. Apply patches with git am, with fixed commit time and identity

- Each run first resets every repository to the commit in the lock and runs `git clean -fd` to remove files added by the previous patch run.
- It then runs `git am --committer-date-is-author-date` with a fixed committer identity. The same patch set therefore yields the same HEAD whenever it is applied.
- If any patch fails, it runs `--abort` and reports that patch's file name.

### D4. The build timestamp comes from the lock

The timestamp on the openwrt line of `upstream.lock` is written to `version.date`, which `scripts/get_source_date_epoch.sh` reads first.

### D5. Package configuration: seed fragments + defconfig + line-by-line verification

- **Composition**: `config/profiles` defines which seed fragments make up each profile; they are concatenated in order and then `make defconfig` runs.
- **Verification**: every line of the seeds (including `# ... is not set`) must appear verbatim in the final `.config`, otherwise it fails. A diffconfig is output at the end.
- **Seed contents**: see `config/*.seed` in the repository. Key points:
  - `IMAGEOPT` and `PREINITOPT` must be enabled explicitly, otherwise defconfig silently drops the custom `TARGET_PREINIT_IP`.
  - zstd for zram needs `KERNEL_ZRAM_BACKEND_ZSTD` and `KERNEL_ZRAM_DEF_COMP_ZSTD` enabled.

### D6. The toolchain relies on configuration only

`CONFIG_EXTRA_OPTIMIZATION` comes after `TARGET_OPTIMIZATION` (`rules.mk:256`), so `-O2 -mcpu=cortex-a72.cortex-a53+crypto` overrides the defaults. The measured command line is `-Os -pipe -mcpu=generic ... -O2 -mcpu=cortex-a72.cortex-a53+crypto`.

When an individual package fails to build under LTO, only that package opts out of LTO: a patch in `patches/packages` adds `PKG_BUILD_FLAGS:=no-lto` to it, and it is registered in `docs/lto-optouts.md`.

### D7. Kernel: two patches plus a config overlay

1. **BBRv3** (`patches/openwrt/0001`): 20 patches go into `hack-6.18/960-bbr3-*`, all kept.
   - Patch 0019 changes the generic `bpf_tcp_ca.c`; without it the build fails.
   - Packaging continues to use upstream's `kmod-tcp-bbr`.
   - Because `MODULE_STRIPPED` removes the version, verification checks the callbacks only BBRv3 has: `bbr_skb_marked_lost` and `bbr_tso_segs`.
2. **Boot script** (`patches/openwrt/0002`): adds `fstools_overlay_compression_type=zstd` to `default.bootscript`.
3. **Kernel config overlay** `config/kernel.config`: `config.sh` links it to `$TREE/env/kernel-config`. Its contents fall into two groups:

```
# f2fs overlay compression (fstools_overlay_compression_type=zstd)
CONFIG_F2FS_FS_COMPRESSION=y
# CONFIG_F2FS_FS_LZO is not set
CONFIG_F2FS_FS_LZ4=y
# CONFIG_F2FS_FS_LZ4HC is not set
CONFIG_F2FS_FS_ZSTD=y

# QEMU virt guest: the shipped kernel boots unchanged in emulation (D14)
CONFIG_PCI_HOST_GENERIC=y
CONFIG_SERIAL_AMBA_PL011=y
CONFIG_SERIAL_AMBA_PL011_CONSOLE=y
CONFIG_VIRTIO_PCI=y
CONFIG_VIRTIO_BLK=y
CONFIG_VIRTIO_NET=y
CONFIG_I6300ESB_WDT=y
# plus every symbol `make listnewconfig` reports for these, with explicit values
```

- **Why the original patch 0001 was removed**: it added F2FS options to `Config-kernel.in`. The overlay is a mechanism upstream supports natively, needs no patch, and does not stop applying when upstream changes. That patch is prepared locally only as an upstream contribution and is no longer in the patch queue.
- **Post-build verification**: after the build, `build.sh` checks that every line of the overlay appears in the kernel `.config`, otherwise it fails.
- **`CONFIG_KERNEL_*` options stay in the seeds** (BTF, `BPF_EVENTS`, cgroup, and so on): these options affect package dependencies and host tool selection, so they remain in the seeds.
- **Alternatives**: add every option to `Config-kernel.in`, or modify `target/.../config-6.18` directly. Both rejected: the former makes the patch grow without end, and the latter stops applying whenever upstream changes.

### D8. Base system

- **LAN address**: set through `TARGET_PREINIT_IP` plus `DEFAULT_LAN_IP_FROM_PREINIT`. This generates `board.d/99-lan-ip`, which takes effect only when the default configuration is generated, so a config-preserving upgrade does not overwrite the user's address.
- **zram**: a uci-defaults script writes 1024 MiB and zstd, only when these two options are not yet set.
- **LuCI**: served by uhttpd through the ucode CGI (`/www/cgi-bin/luci`). `uhttpd-mod-ucode` is only an in-process accelerator and is not required.
- **shell**:
  - The login shell is ash; `profile.d/99-zsh.sh` runs `exec zsh -l` only for an interactive login from ash, and `bash -l` is not switched away.
  - Test data of the zsh plugins is not packaged.

### D9. Local build directory

A 112 GiB ext4 image file on the external SSD is loop-mounted at `/mnt/wrt` inside the VM. `workdir-mount` and `workdir-unmount` come as a pair; `mount` can be run repeatedly, and `--format` only formats an empty image.

### D10. Build environment (flake)

- **Two nixpkgs inputs, each with its own role**:
  - `nixpkgs` (nixos-25.11) provides the build environment and the code-standard tools, for stability.
  - `nixpkgs-unstable` only provides the latest `uv`, plus the emulator-related `qemu`, `dtc`, and `u-boot-tools`, for freshness.
- **Two FHS environments, plus two devShells**:

```
wrt-build-fhs   build packages + build profile            (WRT_FHS=build)
wrt-test-fhs    build packages + test packages + profile  (WRT_FHS=test, superset)
devShell quality  code standards only, same on Linux and macOS (CI check job)
devShell default  quality + both FHS environments on Linux; quality on macOS
```

  - Scripts declare the environment they need with `ensure_fhs build` or `ensure_fhs test`; the test environment contains the build environment and satisfies both.
  - The build environment's profile exports `WRT_BUILD_INPUTS`, pointing to a file that lists every build package path and the profile contents. This is the build environment's fingerprint.
- **Python tools are managed by uv**: ruff, ty, pytest, labgrid, and the Python interpreter itself are pinned by `tests/uv.lock`, not by Nix.
- **Test tool set**: the flake's `testPackages` list collects the daemons and clients that the various peers in the emulation environment need, for example the PPPoE server and package mirror added by later changes. They come from `nixpkgs` and go into the FHS environment; `just test` also runs in the FHS. The foundation adds uv, qemu, dtc, u-boot-tools, `iproute2`, `dnsmasq`, `openssh`, and the `libstdc++` that manylinux wheels need. The closure of full qemu is about 2.2 GiB, but cache.nixos.org has prebuilt binaries, while trimming it ourselves would mean building from source, so we do not trim it.
- **Variables exported by the FHS profile**:
  - `NIX_HARDENING_ENABLE=`
  - `AR=gcc-ar`, `NM=gcc-nm`, `RANLIB=gcc-ranlib`
  - `FAKEROOTDONTTRYCHOWN=1`
  - `WRT_FHS=1`

### D11. CI: two workflows, four jobs

```
check.yml   (every push/PR, no paths filter)          ~2 min
  check: nix develop -c just check

build.yml   (paths-ignore: openspec/**, docs/**, **/*.md)
  host-toolchain  key = hash(arch, tools/, toolchain/, lang/golang, lang/rust,
                             toolchain.seed, WRT_BUILD_INPUTS)
                  miss -> build tools + toolchain -> pack existing paths only
  firmware        needs host-toolchain; unpack + touch; dl/ccache caches;
                  ci profile (ALL_KMODS); manifest.json; unsigned artifacts
  system-test     needs firmware; just test (emulation, TCG); JUnit report
```

- **Why the cache key uses the build environment's fingerprint rather than the contents of `flake.nix` and `flake.lock`**: later changes keep adding tools to the test environment. If the key were computed from file contents, every added tool would rebuild the toolchain (about 80 minutes). The fingerprint changes only with the build packages and the build profile, which is more precise.
- **Why `check.yml` is separate**: it is not subject to path filters, so every push triggers it and it reports quickly; the heavy build runs only when code changes.
- **If the cache does not fit**: when cache usage exceeds 10 GB, store the toolchain archive as a Release asset instead.

### D12. Code standards

| Target | Formatter | Static checks |
|---|---|---|
| shell | `shfmt` (per `.editorconfig`: POSIX dialect, tab indentation, `switch_case_indent`) | `shellcheck` (`.shellcheckrc`: `shell=sh`, enables `add-default-case`, `avoid-nullary-conditions`, `check-extra-masked-returns`, `check-set-e-suppressed`, `check-unassigned-uppercase`, `deprecate-which`, `quote-safe-variables`, `require-variable-braces`) |
| Nix | `nixfmt` | — |
| Python | `ruff format` | `ruff check` (`select = ["ALL"]`, exclusions listed in `tests/ruff.toml` with reasons), `ty check` (`tests/ty.toml`: all rules treated as errors) |
| workflows | — | `actionlint` |
| All text | `.editorconfig` (UTF-8, LF, final newline, trailing whitespace trimmed) | `editorconfig-checker` (except `patches/`) |
| Repository | — | Forbidden-pattern checks (executing or applying remote downloads, in-place `sed -i`), script skeleton check, `gitleaks` (no secrets anywhere in history) |

- **Script skeleton**: every script is organized in the order below; the skeleton check verifies the first three parts.

```sh
#!/bin/sh
# <object>-<verb>: one-line purpose.
# Usage: scripts/<name>.sh [args]
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

<argument parsing>
require_linux; require_workdir; ensure_fhs "$@"   # only the guards the script needs
<main>
```

- **Naming rules**:
  - Pipeline stages are single verbs: `fetch`, `patch`, `config`, `build`, `test`, `check`, `fmt`.
  - Operations on a specific object use "object-verb": `workdir-mount`/`workdir-unmount`, `toolchain-key`/`toolchain-build`/`toolchain-pack`/`toolchain-unpack`, `image-audit`, `env-report`, `runner-prepare`; `test-device` is the device counterpart of `test`.
  - just recipe names match script names and are grouped with `[group(...)]`.
  - Environment variables all use the `WRT_` prefix.
- **One command to check**: `just check` only checks and never modifies; `just fmt` formats. Both run on macOS, with their tools provided by the platform's devShell.

### D13. Test framework

```
tests/
  pyproject.toml  uv.lock  .python-version     project and dependencies (python 3.14, uv-managed)
  pytest.toml  ruff.toml  ty.toml              one configuration file per tool
  conftest.py                                  fixtures: shell, ssh, emulator, net
  targets/emulation.yaml  targets/r4s.yaml     labgrid environments (symmetric)
  wrt_tests/                                   helpers: spec markers, coverage, emu, net
  <domain>/test_<capability>.py                one module per spec capability, e.g.
      firmware/test_rootfs.py      <-> specs/firmware/rootfs
      testing/test_emulation.py    <-> specs/testing/emulation
  unit/test_<helper>.py                        unit tests of wrt_tests/, no target, no @spec
```

- **Directory rules**:
  - Spec tests may only live in `tests/<domain>/test_<capability>.py`, with hyphens in the capability name replaced by underscores. Every test in the module must carry `@spec`, and the capability it names must be the module's own capability.
  - `tests/unit/` only tests the helper code in `wrt_tests/`, connects to no target, and carries no `@spec`.
  - `spec-coverage` enforces both rules, with no exceptions.

- **Mapping to specs**:
  - Each test is annotated with `@spec("firmware/rootfs", "<requirement>", "<scenario>")` for the scenario it covers.
  - `uv run spec-coverage` parses the specs under `openspec/` and the collected tests, and reports which scenarios have no test.
  - Scenarios verified elsewhere, by the build or CI itself (for example build/ci), are recorded in `tests/verified-elsewhere.toml` together with what verifies them.
- **Target selection**:
  - A test is marked `@target("emulation")` or `@target("device")` for a dedicated target, with a reason. Unmarked tests run on both targets.
  - `just test` uses `emulation.yaml`; `just test-device <host>` uses `r4s.yaml`.
  - Power control on the device uses labgrid's `ManualPowerDriver`, which prompts for manual action when power must be cut.
- **Reports**: both targets output JUnit and a terminal summary in the same format, written to `tests/.reports/emulation.xml` and `device.xml` respectively.
- **Router interface**: `wrt_tests.router.Router` offers the same methods on both targets: `run`, `returncode`, `login` (a real interactive login), `put`, `http`, `reboot`, `wait_ready`, `moved_to` (temporarily use another LAN address). Only `reset` differs: the emulator returns to the snapshot, while the device does nothing, so tests on the device must restore the state they change themselves.
- **Compiler-free BPF object**: the test that checks tcx needs a BPF program. Apple's clang has no BPF backend, and device tests can be started from macOS, so `wrt_tests/bpf.py` writes this two-instruction program directly as an ELF object file.

### D14. Emulation environment

```
sysupgrade.img.gz --gunzip (fwtool trailer tolerated)--> disk.raw (read-only base)
   per test: qcow2 overlay on disk.raw  (reset between tests, keep across a power cut)
   p1: kernel.img (FIT) --dumpimage--> Image.lzma --unlzma--> Image
       boot.scr --> bootargs template: ${serial_port}->ttyAMA0, earlycon dropped,
                    ${uuid}-> PARTUUID of p2 from the MBR signature
qemu -machine virt,gic-version=3,dumpdtb=virt.dtb  (same args)  --fdtput-->
       / compatible = "friendlyarm,nanopi-r4s", model = "FriendlyElec NanoPi R4S"

qemu-system-aarch64 -machine virt,gic-version=3 -cpu cortex-a72 -smp 6 -m 4G
  -kernel Image -dtb r4s.dtb -append "<bootargs>"
  -drive if=none,id=d0,file=overlay.qcow2 -device virtio-blk-pci,drive=d0
  -netdev tap,id=wan,ifname=emu-wan -device virtio-net-pci,netdev=wan   # eth0 = WAN
  -netdev tap,id=lan,ifname=emu-lan -device virtio-net-pci,netdev=lan   # eth1 = LAN
  -device i6300esb -action watchdog=reset  -serial <labgrid console>

sandbox: unshare --user --map-root-user --net --mount (rootless)
  br-lan: emu-lan + host side 10.0.0.2 (test runner) + veth -> netns "client-a"
  br-wan: emu-wan + veth -> netns "isp"   (later changes run PPPoE/DHCPv6/STUN here)
```

- **Why impersonate the R4S board**: the R4S `02_network` assigns port roles with `eth1` as LAN and `eth0` as WAN, and the board's upgrade metadata check also depends on it. With `compatible` changed, all of this runs the same code as on the device. Hardware nodes such as LEDs do not exist in the emulator; the related scripts only log a line, with no functional effect.
- **Why TCG**: the local VM has no KVM, and CI emulates aarch64 on x86, so TCG is the only option. One boot takes about one to two minutes; each test module boots once, and disks are restored from a snapshot between tests.
- **Running tests in the FHS environment**: uv-managed Python and manylinux wheels need an FHS to run on NixOS, so tests also run in the FHS environment; the network sandbox is a user namespace nested inside it.
- **Details settled during implementation**:
  - `scripts/test.sh` starts pytest with `unshare --user --map-root-user --net --mount --pid --mount-proc`. The separate PID namespace ensures that as soon as pytest exits (including on interruption), QEMU, dnsmasq, and udhcpc all exit with it, leaving no orphan processes.
  - Each network namespace is held by an `unshare --net sleep` process, and commands enter it with `nsenter`; `/run/netns` is not needed.
  - The serial console must be read continuously: PL011 writes byte by byte, and on a Unix socket each byte takes a whole buffer slot, so if a few hundred bytes go unread the guest stalls. `Emulator` uses a background thread that keeps reading the serial console into memory and a log, and tests wait for output on that record.
  - Snapshots use `savevm`/`loadvm`: the session boots once and takes a `booted` snapshot; after each test it returns to this snapshot, restoring both memory and disk in a few seconds.
  - "Boot complete" is detected by procd's `- init complete -` in `logread`. procd logs through ulog, and once logd is up it no longer writes to the kernel log, so waiting for this line in `dmesg` never succeeds.
  - `ssh` and `scp` in the test environment use one fixed configuration (`-F`): each image has different host keys, and inside the sandbox the host's config files may belong to an unmapped user, which OpenSSH refuses to read.
  - The board script derives MACs from the CID of the SD card (`mmcblk1`). The emulator has no such device, so this step prints an arithmetic error and is skipped, and the ports keep the fixed MACs set by QEMU. All other port role assignment is the same as on the device.
- **What the emulator cannot cover and is left to the device**:
  - The RK3399 BootROM, TPL/SPL, and U-Boot booting from the SD card;
  - The drivers of the two physical ports (stmmac, r8169) and interrupt affinity;
  - A real reset by the DesignWare watchdog;
  - USB3 UAS;
  - Throughput and temperature.

  These all exist as `@target("device")` tests.

## Risks / Trade-offs

- **[BBRv3 fails to apply on a 6.18.y update]** CI stops immediately when a patch fails; we can temporarily return to the previous lock and then rebase the patches.
- **[virt drivers grow the kernel]** Expected at about 100-300 KB, to be measured during implementation. The R4S has no matching devices, so these drivers are never probed.
- **[The overlay misses a sub-option and the kernel config stalls]** Fill in with `listnewconfig` during implementation; post-build line-by-line verification catches config drift.
- **[Differences between emulator and device mistaken as covered]** The coverage report lists device-only scenarios separately; the board identity matches but the hardware nodes differ, and this is documented.
- **[Nested user namespaces unavailable]** Already confirmed working in the OrbStack VM; CI relies on `prepare-runner.sh` to lift the AppArmor restriction, to be confirmed again when implementing `system-test`.
- **[ty is still at 0.0.x]** The version is pinned by `uv.lock`; ty upgrades are handled in the weekly bump, and false positives are recorded in pyproject.
- **[TCG is slow]** Each module boots the VM once and tests are restored from a snapshot; the target duration of the `system-test` job is under 30 minutes.
- **[Exceeding the GitHub cache limit]** See D11 for the fallback.

## Migration Plan

- **New project**: this is a brand-new project with nothing old to migrate. The first delivery is a single-slot image that has passed the emulation tests.
- **Adjustments to the parts already implemented**:
  - Remove patch 0001 and provide the F2FS options through the overlay; the BBRv3 and boot script patches move up to 0001 and 0002;
  - Reorder existing scripts to the common skeleton, add `workdir-unmount`, and rename `audit-image` to `image-audit`;
  - Split CI into `check.yml` and `build.yml`.
- **Rollback**: until the A/B change lands, rollback means reflashing the previous image.

## Open Questions

- The root partition size is tentatively 1024 MiB, to be replanned against SD card capacity when A/B lands.
- The zsh plugins are pinned to v0.7.1 and 0.8.0. Future upgrades go through the normal version update process.
