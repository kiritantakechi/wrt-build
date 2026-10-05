# Optimization

How the firmware's code is optimized, the packages that opt out of it, and what it costs in size (toolchain-o3).

## Compiler flags

`config/toolchain.seed` sets them, all through OpenWrt's configuration: the spec forbids patching `include/target.mk` (firmware/toolchain).

| What | Flags | How |
|---|---|---|
| Target packages | `-Os -pipe -mcpu=generic` and the UB-indicative warnings, then `-fno-caller-saves -fno-plt -O3 -mcpu=<board>` | `TARGET_CFLAGS` is `CONFIG_TARGET_OPTIMIZATION`, then `CONFIG_EXTRA_OPTIMIZATION` (`rules.mk`). Of several `-O` and `-mcpu` flags GCC takes the last, so `-O3` and the board's CPU win. |
| The kernel and its modules | `-fno-caller-saves -O3 -mcpu=<board> -O2` | `KCFLAGS` is `CONFIG_EXTRA_OPTIMIZATION` without `-fno-plt`, then `CONFIG_KERNEL_CFLAGS` (`include/kernel.mk`), so its `-O2` comes last. |
| musl | its own level | `toolchain/musl` filters every `-O` flag out. |
| libgcc and libstdc++ | `-O3` | `toolchain/gcc` filters the `-m` flags out; the toolchain every board shares is built without a board's `-mcpu`. |
| BPF objects | clang `-O2` | `include/bpf.mk` |

**Why the kernel stays at `-O2`.** Upstream Linux supports `-O2` and `-Os` only; it dropped the option that built it at `-O3`. Kbuild puts the build's `KCFLAGS` after its own flags, so without `CONFIG_KERNEL_CFLAGS` the shared `-O3` would win. `tests/firmware/test_toolchain.py` checks that it does not.

**No relaxed floating point.** No flag relaxes IEEE semantics: never `-Ofast`, `-ffast-math`, `-funsafe-math-optimizations`, `-ffinite-math-only`, `-fno-signed-zeros`, `-fno-trapping-math` or `-fassociative-math`. ucode's numbers and their JSON encoding, and the rate and overhead arithmetic of qosify and cake, rely on NaN, infinities and signed zeros. `tests/firmware/test_toolchain.py` checks both sets of flags.

**Undefined behavior.** `-O3` relies on code being free of undefined behavior more than `-O2` does. GCC's UB-indicative warnings and a UBSan build find it, and no shared flag masks it (`docs/undefined-behavior.md`).

The build records both sets of flags in its manifest (`cflags`, `kernel_cflags`), where the tests read them.

## Opt-outs

A package that fails to build is fixed in its source, by a patch stating its upstream status (`docs/patches.md`). Only a package whose upstream code is right, and that no reasonable patch fixes, opts out, in its own Makefile and by a patch, registered below. The registers and the patch queue correspond one to one.

### LTO

All target packages build with LTO (`CONFIG_USE_LTO=y`). A package that fails under LTO opts out with `PKG_BUILD_FLAGS:=no-lto`.

| Package | Repository | Patch | Failure | Date registered |
|---|---|---|---|---|
| (none) | | | | |

### `-O3`

A package that fails under `-O3` opts out with `TARGET_CFLAGS += -O2`, which comes after the shared flags.

| Package | Repository | Patch | Failure | Date registered |
|---|---|---|---|---|
| (none) | | | | |

### Verification log

- 2026-09-28, CI run 36371318405: a full ci profile build (all kmods; 1222 kmod packages, 1382 packages in total) compiled entirely under LTO, and no package needed to opt out.
- 2026-10-05, the dev profile of both boards: every package compiled under `-O3` and LTO, and none needed to opt out. The undefined behavior that GCC's warnings pointed to is fixed by patches (`docs/undefined-behavior.md`).

## Image sizes

The dev profile's images before (`-O2`, 2026-10-04) and after `-O3` (2026-10-05). `-O3` adds about 1.5 MB, 2.5 %, to the root filesystem, which then fills 5.7 % of the 1024 MiB root partition, so no size gate is set.

| Board | | EROFS root | Upgrade image (`sysupgrade.tar.gz`) | Factory image (`factory.img.gz`) |
|---|---|---|---|---|
| NanoPi R4S | `-O2` | 59,351,040 B | 66,057,514 B | 134,783,612 B |
| NanoPi R4S | `-O3` | 60,862,464 B (+2.5 %) | 67,559,235 B (+2.3 %) | 137,787,966 B (+2.2 %) |
| NanoPi R6S | `-O2` | 59,359,232 B | 66,085,377 B | 134,866,601 B |
| NanoPi R6S | `-O3` | 60,882,944 B (+2.6 %) | 67,605,578 B (+2.3 %) | 137,903,410 B (+2.3 %) |
