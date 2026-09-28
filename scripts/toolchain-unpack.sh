#!/bin/sh
# Unpack a toolchain tarball into a freshly fetched tree. The sources were just
# checked out, so their mtimes are newer than the cached build stamps; refresh the
# cached files so make treats the tools and toolchain as up to date.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

archive=${1:?usage: toolchain-unpack.sh <archive.tar.zst>}

require_linux
require_workdir
ensure_fhs "$@"

[ -f "$archive" ] || die "archive not found: $archive"
tar -I zstd -xf "$archive" -C "$TREE"
find "$TREE/staging_dir" "$TREE/build_dir/host" -exec touch -h {} +
info "toolchain restored into $TREE"
