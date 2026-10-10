#!/bin/sh
# toolchain-unpack: restore a toolchain tarball into a freshly fetched tree.
# Usage: scripts/toolchain-unpack.sh <archive.tar.zst>
# The sources were just checked out, so their mtimes are newer than the cached
# build stamps; refresh the cached files so make treats them as up to date. They
# all get the same time: touched one after another, a stamp could end up older
# than a cached file it depends on, and make would rebuild it.
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"

archive=${1:-}
[ -n "${archive}" ] || die "usage: toolchain-unpack <archive.tar.zst>"

require_linux
tree=$(workdir_tree)
ensure_fhs build "$@"

[ -f "${archive}" ] || die "archive not found: ${archive}"
tar -I zstd -xf "${archive}" -C "${tree}"
now=$(date +%s.%N)
set -- "${tree}/staging_dir" "${tree}/build_dir/host"
[ ! -d "${tree}/build_dir/hostpkg" ] || set -- "$@" "${tree}/build_dir/hostpkg"
find "$@" -exec touch -h -d "@${now}" {} +
info "toolchain restored into ${tree}"
