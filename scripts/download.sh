#!/bin/sh
# download: fetch every source the configured tree's build needs into its download directory.
# Usage: scripts/download.sh
# build.sh downloads first as well; CI's firmware job runs this in a step of its
# own before the build, so that it saves the download cache only when every
# download succeeded (release-integrity D6).
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"

require_linux
tree=$(workdir_tree)
ensure_fhs build "$@"

[ -f "${tree}/.config" ] || die "no .config; run 'just config <board>' first"
jobs=${WRT_JOBS:-$(nproc)}
make -C "${tree}" -j"${jobs}" download
