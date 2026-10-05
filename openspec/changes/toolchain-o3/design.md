# Design

## Context

See proposal.md for why. The facts the approach rests on:

**How flags reach the code.**

| What | Its flags | Today |
|---|---|---|
| Target packages | `TARGET_CFLAGS` = `CONFIG_TARGET_OPTIMIZATION`, then `CONFIG_EXTRA_OPTIMIZATION` (`rules.mk`) | `-Os -pipe -mcpu=generic -fno-caller-saves -fno-plt -O2 -mcpu=<board>` |
| The kernel and kmods | `KCFLAGS` = `CONFIG_EXTRA_OPTIMIZATION` without `-fno-plt`, then `CONFIG_KERNEL_CFLAGS` (`include/kernel.mk`) | the extra flags, so `-O2 -mcpu=<board>` |
| musl | `TARGET_CFLAGS` with every `-O` flag filtered out (`toolchain/musl/common.mk`) | musl's own level |
| libgcc and libstdc++ | `TARGET_CFLAGS` with every `-m` flag filtered out (`toolchain/gcc/common.mk`) | `-O2` |
| BPF objects | clang with a fixed `-O2` (`include/bpf.mk`) | `-O2` |

`CONFIG_KERNEL_CFLAGS` is settable under `CONFIG_DEVEL`, which `config/toolchain.seed` already sets, and `CONFIG_TARGET_OPTIMIZATION` under `CONFIG_TARGET_OPTIONS`, a menu of `CONFIG_DEVEL` that holds nothing else on aarch64.

**Seeds and profiles.**
- A profile is a list of seeds (`config/profiles`).
- `compose_seeds` concatenates them. For a board, it merges every `CONFIG_EXTRA_OPTIMIZATION` into the last one and appends the board's `-mcpu`.
- The board-neutral toolchain is built from the composition without a board, and its cache key hashes that composition.
- `configure_tree` fails if `defconfig` drops or changes any line of the composed seed.

**Build logs and the image's packages.**
- `CONFIG_BUILD_LOG=y` in both profiles writes `logs/<package path>/compile.txt` per package.
- OpenWrt writes the list of the packages in each device's image (its `.manifest`) to the board's binary folder.

**Sizes.** The root partition is 1024 MiB. The R4S's EROFS root is about 59 MB today.

**Patches.**
- `patches/openwrt` holds ten patches, `patches/packages` one and `patches/qemu` one. einat carries one of its own, and `docs/upstream` holds two prepared for upstream and not carried.
- `docs/upstream-contributions.md` lists only those meant for upstream.
- 0001 (BBRv3) is the 6.18 port from sbwml/r4s_build_script.
- 0002 edits `target/linux/rockchip/image/default.bootscript`. The A/B images never run that script: their U-Boot boots through `uboot/wrt-ab.env`, which already passes `fstools_overlay_compression_type=zstd`.

## Goals / Non-Goals

**Goals:**
- `-O3` for target userspace, `-O2` for the kernel and no relaxed floating point, all through configuration: the spec forbids patching `include/target.mk`.
- Two independent ways to find undefined behavior, at build time and at run time, each with a gate that keeps what was found fixed.
- An account of every patch: why it exists, and where upstream stands.

**Non-Goals:**
- `-O3` for the kernel: upstream Linux does not support it, and dropped the option that offered it.
- Hardening options (the `_FORTIFY_SOURCE` level, stack protector, RELRO, PIE): a change of their own.
- Profile-guided optimization, and any tuning past `-mcpu`.
- UBSan in CI, and the sanitizers that need a runtime (ASan, MSan, TSan): OpenWrt's musl toolchain ships none.
- Performance measurements: the emulator runs under TCG, which says nothing about a Cortex-A72 or A76, and no board is at hand.

## Decisions

### D1. `-O3` in the shared flags, `-O2` back for the kernel

```
config/toolchain.seed
  CONFIG_TARGET_OPTIMIZATION="-Os -pipe -mcpu=generic <UB warnings, D4>"
  CONFIG_EXTRA_OPTIMIZATION="-fno-caller-saves -fno-plt -O3"   (+ -mcpu=<board> per board)
  CONFIG_KERNEL_CFLAGS="-O2"

target packages   -Os -pipe -mcpu=generic <warnings> -fno-caller-saves -fno-plt -O3 -mcpu=<board>
kernel (KCFLAGS)  -fno-caller-saves -O3 -mcpu=<board> -O2     the last -O wins
musl              its own level (-O filtered)
libgcc/libstdc++  ... -O3 (the -m flags filtered)
BPF               clang -O2
```

**Why these knobs:**
- `CONFIG_TARGET_OPTIMIZATION` comes first in `TARGET_CFLAGS`, so `-O3` there would lose to the `-O2` after it.
- `CONFIG_KERNEL_CFLAGS` is upstream's knob for the kernel's own flags, and it comes last in `KCFLAGS`.
- Filtering `-O3` out of the kernel's flags would have needed a patch to `include/kernel.mk`.

**The toolchain:**
- Its record (`wrt-toolchain.json`) holds the new flags, and its cache key changes.
- GCC's runtime libraries follow `-O3` as every other target library does.

**An existing tree.** `build-acceleration` names every package's prepared stamp after these flags, and rebuilds the toolchains whose recorded flags differ from the configuration's. The new flags therefore rebuild the toolchains and every package in a tree built at `-O2`, with no clean. The kernel follows through Kbuild, which compares each object's command line.

**The manifest** records the flags the kernel build adds (`kernel_cflags`). The board's build computes them from the configuration, so a test that sees only the build outputs can check them.

### D2. No relaxed floating point

`-O3` keeps IEEE semantics. `-Ofast`, the alternative first asked for, adds `-ffast-math`, which assumes that no value is NaN or infinite and that signed zeros do not matter. The image has floating-point code that relies on exactly that: ucode's numbers and their JSON encoding, and the rate and overhead arithmetic of qosify and cake's configuration.

The flags test checks the manifest's package flags and kernel flags for every relaxing option (spec firmware/toolchain).

### D3. A build that fails under `-O3` is fixed in the source

`-O3` produces new warnings, and packages that build with `-Werror` stop on them. Each failure is fixed where the code is wrong, with a patch in the package's own patch directory, carried by the patch series and stating its upstream status (D6).

A package whose upstream code is correct but cannot be fixed reasonably opts out of `-O3` in its own Makefile (`TARGET_CFLAGS += -O2`). The opt-out is registered next to the LTO opt-outs, in `docs/lto-optouts.md`, which becomes `docs/optimization.md`: the flags of D1, the LTO and `-O3` opt-outs, and the sizes of D7.

### D4. UB-indicative warnings, collected per build and reviewed in a register

**Which warnings.** Those of the options the spec lists: diagnostics of out-of-bounds access, overflow, uninitialized reads, use-after-free, aliasing and alignment. Style warnings are left out.

**More of them.**
- Packages that do not enable `-Wall` miss several of these.
- `CONFIG_TARGET_OPTIMIZATION` therefore enables them explicitly: `-Warray-bounds -Wuninitialized -Wmaybe-uninitialized -Wstrict-aliasing -Wuse-after-free -Wdangling-pointer` (all in `-Wall`), and `-Wshift-negative-value`, which not even `-Wall` enables. The rest are on by default.
- That variable reaches the target packages only, never the kernel.

**Collection.**
- `build.sh` takes the packages of the board's image from the image's package list, and maps each to its source package through OpenWrt's package metadata (`tmp/.packageinfo`).
- From each source package's build log it parses GCC's `file:line:col: warning: ... [-Woption]` lines, with the function each falls in.
- OpenWrt rewrites the logs of every package whose compile step it runs, also of one it finds up to date, which then holds only make's time line. So after every make, a failed one included, `build.sh` records the warnings of each log that make wrote with more than that line. The records sit in the board's build directory (`wrt-warnings/`), which lives as long as the objects they describe, and keep each package's warnings from its last real compile.
- It writes `out/<board>/<profile>/warnings.json` from the records of the image's packages, one entry per warning: package, option, file, function, line.
- The warnings travel with the build's outputs, so CI's system tests see them as well.

**The register.**
- `tests/reviewed-warnings.toml` holds the reviewed warnings, one `[[warning]]` table each: package, option, file, function, reason and review date. It is data that a test reads, as `tests/verified-elsewhere.toml` is for the scenarios proven outside the system tests.
- An entry matches a warning on package, option, file and function, never on the line number, so a review survives upstream moving code around.
- Fixed warnings disappear from the build, and their fixes are patches stating their upstream status (D6).
- `docs/undefined-behavior.md` describes how a warning is reviewed, and how and when the `ubsan` profile runs (D5).

**Alternatives considered:**
- `-Werror` on these options would turn every false positive (`-Wmaybe-uninitialized` has many at `-O3`) into a build failure, with no room to review.
- Enabling all of `-Wall` would flood the logs with style warnings and break more `-Werror` builds.

### D5. The `ubsan` profile: UBSan in trap mode, for the packages only

```
config/profiles
  dev:   target toolchain kernel rootfs system datapath services release dev
  ubsan: target toolchain kernel rootfs system datapath services release dev | ubsan
                                                                             ^ board-only seeds
```

**Board-only seeds.**
- Seeds after `|` apply to a board's configuration only. `compose_seeds` without a board stops at `|`.
- The `ubsan` profile thus has the dev profile's toolchain, under the same cache key, and musl, libgcc and libstdc++ stay uninstrumented.

**One line per symbol.**
- `compose_seeds` generalizes its handling of `CONFIG_EXTRA_OPTIMIZATION`: a later seed's line for a symbol replaces an earlier one.
- The composed seed then holds one line per symbol, and the seed check still holds line by line.
- `config/ubsan.seed` sets `CONFIG_TARGET_OPTIMIZATION` to the base value plus `-fsanitize=undefined -fsanitize-trap=undefined`.
- That variable reaches the packages only, so the kernel stays uninstrumented with no further flag.

**Trap mode.** Every check compiles to a trap instruction (`brk #0x3e8` on arm64) instead of a call into libubsan. OpenWrt's musl toolchain has no libubsan, and a trap needs none. The process dies with `SIGTRAP`, and the kernel reports the unhandled exception with the process name and address, if `debug.exception-trace` (`show_unhandled_signals`) is on. arm64 leaves it off by default, so the probe package (below) turns it on from early boot, through `/etc/sysctl.d`.

**Without LTO, and no runtime.** GCC expands UBSan's checks where it generates the code, which under LTO is the link, and lto-wrapper passes no sanitizer option on from the objects: `-fsanitize-trap` counts only on the link line. Many packages link with `LDFLAGS` alone, and libtool drops `-fsanitize-trap` from every link line, so the first ubsan builds' libraries and programs called `__ubsan_handle_*`, and libtool's links failed for want of `-lubsan`. This was found during the implementation; turning `CONFIG_USE_LTO` off did not reach the packages that ask for LTO themselves (mtd, libnftnl) or have their build system do it (glib2).
- A patch to OpenWrt (`patches/openwrt/0017`, `Upstream-Status: Pending`) adds the sanitizer options to `TARGET_LDFLAGS`, so that a link that takes `LDFLAGS` expands the checks as traps, under LTO of a package's own making too (glib2's meson); and it builds every package without OpenWrt's LTO when `TARGET_CFLAGS` asks for traps, so that the checks of a package that libtool links are expanded where its objects are compiled.
- A libtool link still names `-fsanitize=undefined` alone and asks for `-lubsan`. `build.sh` puts an empty `libubsan.a` in the board's staging directory, which answers it and provides nothing.
- After the build, `build.sh` fails if any file of the root filesystem has an undefined `__ubsan_*` symbol, so a check that became a call cannot pass unseen.

**Separate directories.**
- `config.sh` names a build after the board and, for a profile with board-only seeds, after the profile too (`CONFIG_BUILD_SUFFIX=r4s_ubsan`), so instrumented objects never mix with the dev build's.
- Outputs go to `out/<board>/ubsan`.

**Detection.**
- The manifest names the profile.
- In a `ubsan` build, the router fixture reads the kernel log for user-space traps before it restores the snapshot, which would erase them. A test of a module that keeps the router (`module_router`) is checked after it runs, and the boot before the first test.
- A trap fails the test that was running, with the process name and address; a trap while booting fails every test that uses the router.

**The probe.**
- A feed package, `wrt-ubsan-probe`, which only `ubsan.seed` selects, overflows a signed integer on purpose, and turns on the kernel's report of unhandled signals.
- The scenario's test runs it on the router and expects the harness to report its trap.
- This proves the instrumentation, trap mode and detection together. Otherwise a clean run could just mean the instrumentation never happened.

**Where it runs.**
- The profile runs locally on both boards, `just build <board> ubsan` and then `just test <board> ubsan`, once in this change. After that, it reruns after an upstream bump and before a stable release (docs).
- It is not run in CI: a second full build per board does not fit CI's time.

**Triage.**
- Every trap is undefined behavior in code the image runs.
- It is fixed in that code, with a patch meant for upstream, its status `Pending` (D6).
- Alignment findings included: on arm64 the hardware forgives most unaligned loads, but the compiler is entitled to assume alignment, and vectorized code does.

**Alternatives considered:**
- A build per instrumented package, done by hand, is not reproducible.
- Instrumenting the toolchain's libraries too would turn musl's own internals into findings in every process at once.

### D6. Patch audit, and the status each patch states

**Per patch.**
- **Still needed**: not merged upstream at the pinned commit, and not dead code.
- **Minimal and correct**: no unrelated hunks. For C, nothing the warnings and the UBSan run would flag.
- **Message**: current and accurate (what, why, how it was verified), with `Signed-off-by`.
- **Status**: an `Upstream-Status` trailer.

**Known actions.**
- Drop 0002: the A/B images pass the option through `wrt-ab.env`, and `test_overlay_is_compressed_f2fs` guards the result.
- Re-derive BBRv3 from its primary source: the google/bbr v3 branch, as Oleksandr Natalenko rebases it onto 6.18. The current series is then compared against it, and the differences are explained or removed. Its trailer names the source, `Backport [google/bbr v3, rebased for 6.18]`, and its message the comparison.
- Review every other carried patch against the current pins: the series from 0003 on (`build-acceleration`'s 0011 and 0012 included), the packages patches, einat's patch, QEMU's patch, and the two prepared upstream patches.

**Numbers are identities.** A patch keeps its number for good. A dropped patch leaves its number unused, and no patch is renumbered, so a number in a message, a document or a test always means the same patch. A new patch takes the next free number.

**The status in the patch.**
- Every patch file states its upstream status in an `Upstream-Status` trailer (spec build/upstream-pinning), in OpenEmbedded's vocabulary, which Buildroot follows as well: `Pending`, `Submitted [where]`, `Backport [source]`, `Inappropriate [reason]`.
- In a patch made by `git format-patch` the trailer ends the message, where `git interpret-trailers --parse` reads it. A plain diff, as the feed packages' own patches are, carries it in its header.
- The status lives with the patch, so no list elsewhere can drift from the files, and a patch moved or dropped takes its status along.
- `docs/patches.md` replaces `docs/upstream-contributions.md`. It describes the convention, and keeps the write-ups of the `Pending` and `Submitted` patches, with the rule for upstream submissions: none without the maintainer's consent.
- `tests/build/test_upstream_pinning.py` reads every patch file's trailer, and holds the write-ups and the `Pending` and `Submitted` patches in step, both ways.

**Alternative considered:** a table of every patch in `docs/patches.md`, checked against the files. It states each patch's status twice, and the second copy is the one that drifts.

### D7. Size, measured and recorded

For each board, the EROFS root and the upgrade image are measured before and after (dev profile), and the growth is recorded in `docs/optimization.md`. The root partition leaves a margin of over 900 MB, so no size gate is added.

## Risks / Trade-offs

- [`-O3` makes `-Wmaybe-uninitialized` and `-Wstringop-overflow` report more false positives] → They go to `tests/reviewed-warnings.toml`, each reviewed with a reason. No blanket suppression.
- [`-Werror` packages stop building] → Fixed in the source (D3). An opt-out only as a registered last resort.
- [The UBSan run finds more than this change can fix] → The findings are listed as they come. If they outgrow the change, the scope question goes back to the maintainer before anything is masked.
- [The first CI run rebuilds the toolchain and every package] → Expected once. After `build-acceleration`, the host stage rebuilds with its compiler cache serving what the flags do not touch, and a firmware job compiles its packages cold in 1.5 to 2.5 hours instead of the 3.5 to 4.75 of a cold run today (docs/ci.md). The compiler caches recover on the next run.
- [The kernel briefly gets `-O3` if `CONFIG_KERNEL_CFLAGS` is lost] → The kernel flags test (spec firmware/toolchain) fails such a build.
- [The board-only seeds and the one-line-per-symbol merge change `compose_seeds` for every profile] → For dev and ci the composed seed only loses duplicate lines. The toolchain key changes, as it does anyway with `-O3`.
- [The `ubsan` profile costs about 45 GB per board, and a full build and test run each time] → It is kept off CI and run at the points D5 names. Its build directories can be deleted in between.

## Migration Plan

Firmware only: routers take it with the next release. The first stable release has not been published yet, so no device runs `-O2` code that would need care. Rollback means reverting the seeds and the patches.

## Open Questions

- ~~Where Oleksandr Natalenko publishes the 6.18 BBRv3 rebase.~~ Resolved: pf-kernel (codeberg.org/pf-kernel/linux), branch `pf-6.18`, as one commit, `a05ea4b4cef3`, on Linux 6.18.0. Rebased onto 6.18.52, it differs from the earlier series in a congestion control flag bit that collides with AccECN there, which 6.18.y backported (patch 0001 explains the rest).
- google/bbr has since moved BBRv3 into a module of its own, `tcp_bbr3`, named `bbr3`, beside BBRv1 (branch `bbr-v3-2026-09-16-01`, on Linux 7.1), and pf-kernel follows it from 7.3 on. Adopting that form renames the firmware's congestion control (spec firmware/kernel), so it is left to a change of its own, with the kernel bump that brings it.
