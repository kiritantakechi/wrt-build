#!/bin/sh
# Print the host-toolchain cache key as key=<value> (for $GITHUB_OUTPUT). The key
# covers exactly the inputs that change the cached tools and cross toolchain.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
require_workdir
ensure_fhs "$@"

[ -f "$TREE/feeds.conf" ] || die "no source tree; run 'just fetch' and 'just patch' first"

digest=$({
	uname -m
	git -C "$TREE" rev-parse HEAD:tools HEAD:toolchain
	git -C "$TREE/feeds/packages" rev-parse HEAD:lang/golang HEAD:lang/rust
	cat "$REPO_DIR/config/toolchain.seed" "$REPO_DIR/flake.nix" "$REPO_DIR/flake.lock"
} | sha256sum | cut -d' ' -f1)
printf 'key=toolchain-v1-%s\n' "$digest"
