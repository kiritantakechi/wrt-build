#!/bin/sh
# toolchain-build: build the host tools and the cross toolchain of the configured tree.
# Usage: scripts/toolchain-build.sh
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
require_workdir
ensure_fhs build "$@"

[ -f "${TREE}/.config" ] || die "no .config; run 'just config <profile>' first"
jobs=${WRT_JOBS:-$(nproc)}
make -C "${TREE}" -j"${jobs}" tools/install toolchain/install
