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

The build reads each package's log (`logs/<package>/compile.txt`). What GCC finds while it links an LTO package depends on the order in which the linker hands it the input files: mold hands them over in the command line order (patch 0018), so that every link of the same objects finds the same warnings. Make writes each job's output to the log whole (patch 0016), and so does the make that GCC runs for a link's LTO jobs (LTRANS, patch 0020), so that diagnostics do not interleave in the log; the parser also drops a chain of inlined calls that its diagnostic does not follow, so an interleaved warning would lose its function rather than take another's. OpenWrt rewrites the log of every package whose compile step it runs, even one it finds up to date, which then holds only make's time line. So after every make, a failed one included, the build records the warnings of each log that holds a compile, and keeps the record of a package whose log holds only that line; a package that compiles without a word, as base-files does, gets an empty record the first time. The records stay in the board's build directory (`build_dir/target-*/wrt-warnings`) as long as the objects they describe, and an incremental build reports the warnings of every package, not only of those it compiled.

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

## UBSan at run time

GCC warns only of what it sees while compiling. The `ubsan` profile instruments every target package with UBSan, so undefined behavior that the system tests make the code run stops the process (toolchain-o3 D5).

**What it builds.** The dev profile, with `config/ubsan.seed` after it: `CONFIG_TARGET_OPTIMIZATION` gains `-fsanitize=undefined -fsanitize-trap=undefined`. Every check then compiles to a trap instruction (`brk #0x3e8` on arm64) instead of a call into libubsan, which OpenWrt's musl toolchain does not have. The seed is board-only (after the `|` in `config/profiles`): the toolchain is the dev profile's, under the same key, so musl, libgcc and libstdc++ stay uninstrumented, and so does the kernel, which that option never reaches. The build has directories of its own (`build_dir/target-*_r4s_ubsan`), and its outputs go to `out/<board>/ubsan`.

**Traps under LTO.** GCC expands UBSan's checks where it generates the code, which under LTO is the link, and takes `-fsanitize-trap` from the link line alone. So the link needs the sanitizer options too: OpenWrt's package build links with those of the compile (patch 0017), which covers links that take `LDFLAGS`, make's built-in rule and meson's among them, and libtool passes every `-fsanitize` option on (patch 0019), where it used to drop `-fsanitize-trap`; and a package that carries its own copy of libtool gets the same change in it (patch 0021). The profile thus keeps LTO, as the shipped builds do. After the build, `build.sh` fails if any file of the root filesystem calls into a runtime (`__ubsan_*`).

**How a trap shows.** The process dies with `SIGTRAP`. The image of this profile alone holds `wrt-ubsan-probe`, which turns on the kernel's report of processes killed by a signal they do not handle (`debug.exception-trace`, off by default on arm64), so the kernel log names the process, its pid and the address. The harness reads that log after every test that used the router, before the snapshot erases it, and fails the test with what trapped; a trap in a fixture that keeps the router for a module, outside its tests, fails the module's last test, and a trap while the router booted fails every test that uses it (`tests/wrt_tests/ubsan.py`). The probe overflows a signed integer on purpose, and the test of the scenario "Trap during a system test" runs it and expects that failure: a run without any trap could otherwise just mean the instrumentation never happened.

**Running it.** On each board:

```
just build r4s ubsan
just test r4s ubsan
```

The register checks of the warnings skip in this profile: it ships nothing, and the instrumentation changes what GCC warns of. It is not run in CI, where a second full build per board does not fit. It runs after an upstream bump and before a stable release, and its build and staging directories, about 18 GB per board, can be deleted in between.

**A trap** is undefined behavior in code the image runs. It is fixed in that code, with a patch meant for upstream, its status `Pending`, like a warning that is undefined behavior; alignment findings included, since the compiler may assume alignment, and vectorized code does.

### Runs

Each run is the whole system suite of one board on a `ubsan` build; a trap is fixed where it lies, and the board is built and tested again. The R4S's last run predates patches 0031 and 0032, which the R6S's runs found; both only take undefined behavior away.

| Date | Board | Result | What trapped, and the fix |
|---|---|---|---|
| 2026-10-06 | R4S | No system test could reach the router | netifd, adding a delegated prefix, so the network never came up (patch 0026); `ubus call`, printing a 64-bit value (0025); busybox `printf` (0022); logd, aligning its entries (0023). Reading logd for 0023 found its copy into a grown buffer (0024) |
| 2026-10-06 | R4S | The WAN never came up | pppd's seed, at every start (0027) |
| 2026-10-06 | R4S | 258 passed, 2 failed, 91 errors | nft, in `ct_print()`, which GCC had made a single trap under LTO (0028), and every test that lists the ruleset with it; odhcp6c's first Solicit (0029); LuCI's string hash, in a page in Simplified Chinese (luci 0002). The probe's test read the trap's status through SSH, which reports 255 (fixed in the test) |
| 2026-10-10 | R4S | 316 passed, 33 errors | `block info`, on the btrfs data disk that `wrt-data init` had just made (0030), so no module got its data disk. The harness did not report it: the trap came in a module fixture, outside any test, and the module's end restored the snapshot over it; `module_router` now reads it first |
| 2026-10-10 | R4S | 348 passed, 1 failed, 7 errors | wsdd2's seed, on almost every start (packages 0005). `test_inbound_ipv6_is_rejected` was refused a LAN connection once, with no trap; it passed in the runs before and after |
| 2026-10-10 | R4S | 349 passed, 5 skipped, no trap | |
| 2026-10-10 | R6S | 347 passed, 4 failed, 1 error | uhttpd, in ucode's ubus module, converting a reply with a 64-bit value (0031), so the metrics stopped after their first collector. And `test_boards_build_apart` expected the board's name as the build directories' suffix, which a ubsan build's is not; the manifest now names the build (`build`) |
| 2026-10-10 | R6S | 350 passed, 4 skipped, 1 error | qosify, reading the IP header of a DNS reply two bytes off its alignment (0032), once, during a trial boot |
| 2026-10-10 | R6S | 350 passed, 4 skipped, no trap | |
