#!/bin/sh
# toolchain-pack: pack the built host tools and the toolchain of every language into a tarball.
# Usage: scripts/toolchain-pack.sh <archive.tar.zst>
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

archive=${1:-}
[ -n "${archive}" ] || die "usage: toolchain-pack <archive.tar.zst>"

require_linux
require_workdir
ensure_fhs build "$@"

cd "${TREE}"
# The toolchain the tree is configured for, as toolchain-build leaves it; not a
# directory another configuration left, such as the one buildbot mode stamps
# before defconfig has run (staging_dir/toolchain-_gcc-_).
toolchain_dir=$(make -s val.TOOLCHAIN_DIR)
toolchain="staging_dir/${toolchain_dir##*/}"
# Without its compile stamp, make world rebuilds the toolchain (toolchain-build).
[ -f "${toolchain}/stamp/.toolchain_compile" ] ||
	die "the toolchain has no compile stamp; build it with toolchain-build"
# staging_dir/hostpkg holds the host packages, Go and Rust among them.
set --
for path in staging_dir/host staging_dir/hostpkg "${toolchain}" build_dir/host; do
	if [ -e "${path}" ]; then
		set -- "$@" "${path}"
	fi
done
[ "$#" -gt 0 ] || die "nothing to pack; build the toolchain first"
# Of the host packages' build directories, only the stamps that tell make they
# are built: their empty dot files (.prepared*, .configured, .built*). Rust's
# build tree alone takes 20 GB, and nothing reads it once Rust is installed.
stamps=$(mktemp)
trap 'rm -f "${stamps}"' EXIT INT TERM
if [ -d build_dir/hostpkg ]; then
	find build_dir/hostpkg -mindepth 2 -maxdepth 2 -type f -name '.*' -size 0 >"${stamps}"
fi
tar -I 'zstd -T0 -3' -cf "${archive}" "$@" -T "${stamps}"
ls -lh "${archive}"
