#!/bin/sh
# toolchain-pack: pack the built host tools and cross toolchain into a tarball.
# Usage: scripts/toolchain-pack.sh <archive.tar.zst>
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

archive=${1:-}
[ -n "${archive}" ] || die "usage: toolchain-pack <archive.tar.zst>"

require_linux
require_workdir
ensure_fhs build "$@"

# staging_dir/hostpkg only exists once host packages (golang, rust, ...) are built.
cd "${TREE}"
# Without the compile stamp, make world rebuilds the toolchain (toolchain-build).
set -- staging_dir/toolchain-*/stamp/.toolchain_compile
[ -f "$1" ] || die "the toolchain has no compile stamp; build it with toolchain-build"
set --
for path in staging_dir/host staging_dir/hostpkg staging_dir/toolchain-* build_dir/host; do
	if [ -e "${path}" ]; then
		set -- "$@" "${path}"
	fi
done
[ "$#" -gt 0 ] || die "nothing to pack; build the toolchain first"
tar -I 'zstd -T0 -3' -cf "${archive}" "$@"
ls -lh "${archive}"
