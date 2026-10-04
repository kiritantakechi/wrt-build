# Undefined behavior

Target packages build at `-O3` (`config/toolchain.seed`). The more a compiler optimizes, the more it relies on the program having no undefined behavior: an out-of-bounds read, a signed overflow or a read of an uninitialized variable that happened to work at `-O2` can turn into wrong code. Such code is fixed where it is wrong, never masked by a shared compiler flag such as `-fwrapv` or `-fno-strict-aliasing` (spec quality/undefined-behavior).

Two independent checks find it: GCC's warnings at build time, and UBSan at run time.

## UB-indicative warnings

GCC diagnoses some undefined behavior while it optimizes. These options are the UB-indicative ones (`UB_WARNINGS` in `scripts/lib.sh`):

| Undefined behavior | Options |
|---|---|
| Out-of-bounds access | `-Warray-bounds`, `-Wstringop-overflow`, `-Wstringop-overread`, `-Waggressive-loop-optimizations` |
| Uninitialized read | `-Wuninitialized`, `-Wmaybe-uninitialized` |
| Lifetime | `-Wuse-after-free`, `-Wdangling-pointer`, `-Wfree-nonheap-object` |
| Shifts | `-Wshift-count-overflow`, `-Wshift-count-negative`, `-Wshift-negative-value` |
| Aliasing and alignment | `-Wstrict-aliasing`, `-Waddress-of-packed-member` |

Packages that do not enable `-Wall` would miss several of them, and `-Wshift-negative-value` is not even in `-Wall`, so `CONFIG_TARGET_OPTIMIZATION` (`config/toolchain.seed`) enables those explicitly for every target package. The rest are on by default. The kernel builds with its own flags, and is outside this check.

### The report

`scripts/build.sh` writes `out/<board>/<profile>/warnings.json`: every warning of these options in the build of a package the image ships, with its package, option, file, function and line.

- **Package**: the source package, named after the directory of its Makefile.
- **File**: the path as GCC printed it, without the build's directories. A file of the package's build directory is named relative to it (`src/cache.c`), and one of the toolchain or staging directory relative to that (`include/fortify/string.h`).
- **Function**: the one GCC names before the warning. For code inlined into another function, it is the outermost function, and the file and line are those of its call. It is empty outside any function.

The build reads each package's log (`logs/<package>/compile.txt`). OpenWrt rewrites the log of every package whose compile step it runs, even one it finds up to date, which then holds only make's time line. So after every make, a failed one included, the build records the warnings of each log that holds a compile. The records stay in the board's build directory (`build_dir/target-*/wrt-warnings`) as long as the objects they describe, and an incremental build reports the warnings of every package, not only of those it compiled.

### The checks

The system tests check every build's report against the register, `tests/reviewed-warnings.toml` (`tests/quality/test_undefined_behavior.py`):

- **Unreviewed warning**: a warning no review covers fails, named with its package, option and location.
- **Stale review**: a review that matches no warning of the build fails, named. The code changed, upstream fixed it, or a patch did, and the review goes.

To run just these checks against a build: `just test r4s dev quality/test_undefined_behavior.py`.

### Reviewing a warning

1. Read the code at the warning, and the paths that lead to it. For a `-Wmaybe-uninitialized` or a `-Wstringop-*` warning, follow the values GCC assumed, which the warning's notes name.
2. If it is undefined behavior, fix the code with a patch in the package's patch directory (in `patches/packages` for the packages feed, in the OpenWrt series for OpenWrt's own packages). Its status is `Pending`, with a write-up in `docs/patches.md`, as for every patch meant for upstream. The warning then leaves the report.
3. If it is not, add a review to the register: the package, option, file and function as the report names them, the reason, and the date. The reason says why the code is defined, for example the invariant that keeps an index in bounds, or the path that GCC cannot rule out but the caller does. A review matches on package, option, file and function, never on the line, so it survives upstream moving code around. If only some boards' builds emit the warning (GCC's findings depend on the optimization, and so on `-mcpu`), `boards` limits the review to them.

A warning is never silenced in the code (`#pragma GCC diagnostic`), and no `-Wno-*` option is added for it.
