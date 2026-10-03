#!/bin/sh
# toolchain-key: print the host-toolchain cache key as key=<value>.
# Usage: scripts/toolchain-key.sh [profile] >>"$GITHUB_OUTPUT"   (default dev)
# The key covers exactly the inputs that change the cached host tools and cross
# toolchain of the profile (design D11): among them the configuration
# toolchain-build.sh builds it from.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

profile=${1:-dev}

require_linux
require_workdir
ensure_fhs build "$@"

[ -f "${TREE}/feeds.conf" ] || die "no source tree; run 'just fetch' and 'just patch' first"
[ -n "${WRT_BUILD_INPUTS:-}" ] || die "WRT_BUILD_INPUTS is not set; the build environment is too old"

arch=$(uname -m)
trees=$(git -C "${TREE}" rev-parse HEAD:tools HEAD:toolchain)
langs=$(git -C "${TREE}/feeds/packages" rev-parse HEAD:lang/golang HEAD:lang/rust)
# The build files that name the stamps of the Go and Rust host builds, which the
# archive carries (build_dir/hostpkg): a prepared stamp hashes the package's
# files and configuration as these define it (build-acceleration D2).
stamps=$(git -C "${TREE}" rev-parse HEAD:include/depends.mk HEAD:include/host-build.mk HEAD:rules.mk)
# The board-neutral configuration of the profile, as toolchain-build.sh composes
# it: every seed of the profile and every board's device (board-model D2).
configuration=$(mktemp)
trap 'rm -f "${configuration}"' EXIT INT TERM
compose_seeds "${profile}" "" "${configuration}"
seed=$(sha256sum <"${configuration}")
# Build environment fingerprint (flake.nix: buildInputsId): the store paths of the
# host packages plus the build profile. Test and quality tooling are not part of
# it, so adding them keeps the cached toolchain.
environment=${WRT_BUILD_INPUTS##*/}
# The scripts that build and pack the archive decide what it holds.
recipe=$(cat "${REPO_DIR}"/scripts/toolchain-build.sh "${REPO_DIR}"/scripts/toolchain-pack.sh | sha256sum)

digest=$(printf '%s\n' "${arch}" "${trees}" "${langs}" "${stamps}" "${seed}" "${environment}" "${recipe}" | sha256sum)
printf 'key=toolchain-%s\n' "${digest%% *}"
