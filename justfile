# Entry points for building the NanoPi R4S firmware. Run inside `nix develop`.
# Build recipes need WRT_WORKDIR (a case-sensitive directory outside this repo)
# and a Linux host; see docs/dev-setup.md.

set shell := ["sh", "-eu", "-c"]

# List the available recipes
default:
    @just --list

# Print the pinned host tool versions (must match between the local VM and CI)
env-report:
    scripts/env-report.sh

# Check out the pinned upstream sources (upstream.lock) into $WRT_WORKDIR/openwrt
fetch:
    scripts/fetch.sh

# Apply patches/<repo>/*.patch on top of the pinned sources
patch:
    scripts/patch.sh

# Compose config/*.seed for a profile (dev, ci) and verify the result
config profile="dev":
    scripts/config.sh {{ profile }}

# Fetch, patch, configure and build a profile
build profile="dev": fetch patch (config profile)
    scripts/build.sh {{ profile }}

# Check a built sysupgrade image against the base-system spec
audit-image image:
    scripts/audit-image.sh {{ image }}

# Repository checks (forbidden patterns, shellcheck); runs on any host
lint:
    scripts/lint.sh
