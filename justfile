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

# Compose a board's configuration, a profile's seeds (dev, ci) and the board's, and verify it
[group('build')]
config board profile="dev":
    scripts/config.sh {{ board }} {{ profile }}

# Print every board's id (boards/*.json), or check the named ones, as a JSON list
[group('build')]
boards *ids:
    scripts/boards.sh {{ ids }}

# Check the board, fetch, patch, build the toolchain, then configure and build the board
[group('build')]
build board profile="dev": (boards board) fetch patch (toolchain-build profile) (config board profile)
    scripts/build.sh {{ board }} {{ profile }}

# Check a built sysupgrade image against the base-system spec
[group('image')]
image-audit image:
    scripts/image-audit.sh {{ image }}

# Run the system tests against the emulator, booting a board's built image
[group('test')]
test board profile="dev" *args:
    scripts/test.sh {{ board }} {{ profile }} {{ args }}

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

# Prepare a board's upgrade drill base: its latest stable release, or this build before one
[group('release')]
drill-base board:
    scripts/drill-base.sh {{ board }}

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

# Create the private configuration repository and, if missing, the age key
[group('ops')]
config-init directory:
    scripts/config-init.sh {{ directory }}

# Push the private configuration ($WRT_CONFIG_DIR) to a router over SSH
[group('ops')]
config-push host *args:
    scripts/config-push.sh {{ host }} {{ args }}

# Prepare a GitHub-hosted runner (CI only)
[group('ci')]
runner-prepare:
    scripts/runner-prepare.sh

# Print the host-toolchain cache key of a profile's toolchain
[group('ci')]
toolchain-key profile="dev":
    scripts/toolchain-key.sh {{ profile }}

# Print the compiler cache key of a stage (host, or a board)
[group('ci')]
compiler-cache-key stage:
    scripts/compiler-cache-key.sh {{ stage }}

# Build the host tools and the board-neutral cross toolchain
[group('ci')]
toolchain-build profile="dev":
    scripts/toolchain-build.sh {{ profile }}

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
