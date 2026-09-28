# LTO opt-out register

All target packages build with LTO by default (`CONFIG_USE_LTO=y`). When a package fails to build under LTO, only that package opts out: add `PKG_BUILD_FLAGS:=no-lto` to its Makefile. The change lives as a patch in `patches/<feed>/` and is registered in the table below. The register and the patch queue must correspond one-to-one.

| Package | Repository | Patch | Failure | Date registered |
|---|---|---|---|---|
| (none yet) | | | | |

## Verification log

- 2026-09-28, CI run 36371318405: a full ci profile build (all kmods; 1222 kmod packages, 1382 packages in total) compiled entirely under LTO, and no package needed to opt out.
