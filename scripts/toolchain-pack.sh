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
# staging_dir/hostpkg only exists once host packages (golang, rust, ...) are built.
paths=
for path in staging_dir/host staging_dir/hostpkg staging_dir/toolchain-* build_dir/host; do
	[ -e "$path" ] && paths="$paths $path"
done
[ -n "$paths" ] || die "nothing to pack; build the toolchain first"
# shellcheck disable=SC2086 # paths is a whitespace-separated list without spaces
tar -I 'zstd -T0 -3' -cf "$archive" $paths
ls -lh "$archive"
