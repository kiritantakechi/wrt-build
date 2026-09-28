# Entry points of wrt-build. Every recipe runs the script of the same name in
# scripts/ (design D12). Run inside `nix develop`; build and test recipes need a
# Linux host and WRT_WORKDIR (see docs/dev-setup.md).

set shell := ["sh", "-eu", "-c"]

# List the available recipes
default:
    @just --list

# Print the pinned host tool versions (identical on the local VM and CI)
[group('build')]
env-report:
    scripts/env-report.sh

# Check out the pinned upstream sources (upstream.lock) into $WRT_WORKDIR/openwrt
[group('build')]
fetch:
    scripts/fetch.sh

# Apply patches/<repo>/*.patch on top of the pinned sources
[group('build')]
patch:
    scripts/patch.sh

# Compose config/*.seed for a profile (dev, ci) and verify the result
[group('build')]
config profile="dev":
    scripts/config.sh {{ profile }}

# Fetch, patch, configure and build a profile
[group('build')]
build profile="dev": fetch patch (config profile)
    scripts/build.sh {{ profile }}

# Check a built sysupgrade image against the base-system spec
[group('image')]
image-audit image:
    scripts/image-audit.sh {{ image }}

# Run every code-standard check; changes nothing (any host)
[group('quality')]
check:
    scripts/check.sh

# Format every file that has a formatter (any host)
[group('quality')]
fmt:
    scripts/fmt.sh

# Prepare a GitHub-hosted runner (CI only)
[group('ci')]
runner-prepare:
    scripts/runner-prepare.sh

# Print the host-toolchain cache key
[group('ci')]
toolchain-key:
    scripts/toolchain-key.sh

# Build the host tools and the cross toolchain
[group('ci')]
toolchain-build:
    scripts/toolchain-build.sh

# Pack the host tools and cross toolchain into an archive
[group('ci')]
toolchain-pack archive:
    scripts/toolchain-pack.sh {{ archive }}

# Restore the host tools and cross toolchain from an archive
[group('ci')]
toolchain-unpack archive:
    scripts/toolchain-unpack.sh {{ archive }}

# Loop-mount the build volume in the Linux VM (root)
[group('workdir')]
workdir-mount *args:
    scripts/workdir-mount.sh {{ args }}

# Flush and unmount the build volume before unplugging the SSD (root)
[group('workdir')]
workdir-unmount *args:
    scripts/workdir-unmount.sh {{ args }}
