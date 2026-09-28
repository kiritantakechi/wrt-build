#!/bin/sh
# toolchain-build: build the host tools and the cross toolchain of the configured tree.
# Usage: scripts/toolchain-build.sh
# 'make world' skips toolchain/compile only while the toolchain's compile stamp is
# up to date. toolchain/install does not write that stamp, and without it world
# rebuilt the whole cross toolchain on top of the cached one, because the packed
# archive has no build_dir/toolchain-*. So the stamp is built here as well.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
require_workdir
ensure_fhs build "$@"

[ -f "${TREE}/.config" ] || die "no .config; run 'just config <profile>' first"
jobs=${WRT_JOBS:-$(nproc)}
make -C "${TREE}" -j"${jobs}" tools/install toolchain/install
# The stamp that toolchain/Makefile defines: stampfile toolchain,compile in $(TOOLCHAIN_DIR).
toolchain_dir=$(make -C "${TREE}" -s val.TOOLCHAIN_DIR)
[ -d "${toolchain_dir}" ] || die "no toolchain directory at '${toolchain_dir}'"
make -C "${TREE}" "${toolchain_dir}/stamp/.toolchain_compile"
