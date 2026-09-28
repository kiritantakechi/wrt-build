#!/bin/sh
# Build the host tools and the cross toolchain for the configured tree.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
require_workdir
ensure_fhs "$@"

[ -f "$TREE/.config" ] || die "no .config; run 'just config <profile>' first"
jobs=${WRT_JOBS:-$(nproc)}
make -C "$TREE" -j"$jobs" tools/install toolchain/install
