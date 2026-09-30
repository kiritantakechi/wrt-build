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

# Run the system tests against the emulator, booting a built profile's image
[group('test')]
test profile="dev" *args:
    scripts/test.sh {{ profile }} {{ args }}

# Open the host kernel's PPP to the test sandbox, after each VM restart (root)
[group('test')]
sandbox-prepare:
    scripts/sandbox-prepare.sh

# Check the packet marks of the configuration templates against config/marks.tsv (any host)
[group('quality')]
marks-check *dirs:
    scripts/marks-check.sh {{ dirs }}

# Run the code-standard checks, all or the named ones; changes nothing (any host)
[group('quality')]
check *names:
    scripts/check.sh {{ names }}

# Format with all formatters or the named ones (any host)
[group('quality')]
fmt *names:
    scripts/fmt.sh {{ names }}

# Create release keys: public halves into wrt-keyring, --upload the private (maintainer)
[group('release')]
release-keys directory *args:
    nix run .#sign-tools -- scripts/release-keys.sh {{ directory }} {{ args }}

# Sign one build's outputs for release with the pinned signing tools (no build tools)
[group('release')]
release-sign build signed *args:
    nix run .#sign-tools -- scripts/release-sign.sh {{ build }} {{ signed }} {{ args }}

# Prepare the upgrade drill's base: the latest stable release, or this build before one
[group('release')]
drill-base:
    scripts/drill-base.sh

# Assemble a signed build into a release; --upload publishes it on GitHub
[group('release')]
release-publish signed release *args:
    scripts/release-publish.sh {{ signed }} {{ release }} {{ args }}

# Move upstream.lock to the upstream heads; the pull request's text to a file
[group('release')]
upstream-bump description *args:
    scripts/upstream-bump.sh {{ description }} {{ args }}

# Check the repository's GitHub settings the release pipeline relies on
[group('release')]
github-audit *args:
    scripts/github-audit.sh {{ args }}

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
