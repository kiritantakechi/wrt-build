#!/bin/sh
# toolchain-key: print the host-toolchain cache key as key=<value>.
# Usage: scripts/toolchain-key.sh >>"$GITHUB_OUTPUT"
# The key covers exactly the inputs that change the cached host tools and cross
# toolchain (design D11).
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
require_workdir
ensure_fhs build "$@"

[ -f "${TREE}/feeds.conf" ] || die "no source tree; run 'just fetch' and 'just patch' first"
[ -n "${WRT_BUILD_INPUTS:-}" ] || die "WRT_BUILD_INPUTS is not set; the build environment is too old"

arch=$(uname -m)
trees=$(git -C "${TREE}" rev-parse HEAD:tools HEAD:toolchain)
langs=$(git -C "${TREE}/feeds/packages" rev-parse HEAD:lang/golang HEAD:lang/rust)
seed=$(cat "${REPO_DIR}/config/toolchain.seed")
# Build environment fingerprint (flake.nix: buildInputsId): the store paths of the
# host packages plus the build profile. Test and quality tooling are not part of
# it, so adding them keeps the cached toolchain.
environment=${WRT_BUILD_INPUTS##*/}

digest=$(printf '%s\n' "${arch}" "${trees}" "${langs}" "${seed}" "${environment}" | sha256sum)
# The version changes with what the archive holds; v3 adds the toolchain's compile
# stamp (toolchain-build).
printf 'key=toolchain-v3-%s\n' "${digest%% *}"
