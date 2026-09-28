#!/bin/sh
# Pack the built host tools and cross toolchain into one zstd tarball.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

archive=${1:?usage: toolchain-pack.sh <archive.tar.zst>}

require_linux
require_workdir
ensure_fhs "$@"

cd "$TREE"
# shellcheck disable=SC2046 # the glob expands to the toolchain directory
tar -I 'zstd -T0 -3' -cf "$archive" \
	staging_dir/host staging_dir/hostpkg $(ls -d staging_dir/toolchain-*) build_dir/host
ls -lh "$archive"
