#!/bin/sh
# Print the host-toolchain cache key as key=<value> (for $GITHUB_OUTPUT). The key
# covers exactly the inputs that change the cached tools and cross toolchain.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
require_workdir
ensure_fhs build "$@"

[ -f "$TREE/feeds.conf" ] || die "no source tree; run 'just fetch' and 'just patch' first"
[ -n "${WRT_BUILD_INPUTS:-}" ] || die "WRT_BUILD_INPUTS is not set; the build environment is too old"

digest=$({
	uname -m
	git -C "$TREE" rev-parse HEAD:tools HEAD:toolchain
	git -C "$TREE/feeds/packages" rev-parse HEAD:lang/golang HEAD:lang/rust
	cat "$REPO_DIR/config/toolchain.seed"
	# Build environment fingerprint (flake.nix: buildInputsId): the store paths of
	# the host packages plus the build profile. Test and quality tooling are not
	# part of it, so adding them keeps the cached toolchain.
	basename -- "$WRT_BUILD_INPUTS"
} | sha256sum | cut -d' ' -f1)
printf 'key=toolchain-v2-%s\n' "$digest"
