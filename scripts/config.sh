#!/bin/sh
# config: compose a board's configuration and verify the result.
# Usage: scripts/config.sh <board> [profile]   (boards/<board>.json; profiles: config/profiles, default dev)
# The profile's seeds, then the board's seed (board-model D2): the board builds in
# build and output directories of its own. Fails on an unknown board before the
# tree is touched, and if make defconfig dropped or changed any seed line
# (renamed or removed options, unmet dependencies). Writes the composed seeds and
# the diffconfig to $WRT_WORKDIR/out/<board>.
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"
use boards seeds tree

board=${1:-}
profile=${2:-dev}

require_linux
tree=$(workdir_tree)
ensure_fhs build "$@"

[ -n "${board}" ] || die "usage: config <board> [profile]"
board_field "${board}" .device >/dev/null
[ -f "${tree}/feeds.conf" ] || die "no source tree; run 'just fetch' and 'just patch' first"

link_tree "${tree}"
write_board_table "${tree}"
out="${WRT_WORKDIR}/out/${board}"
mkdir -p "${out}"
wanted="${out}/seed-${profile}.config"
compose_seeds "${tree}" "${profile}" "${board}" "${wanted}"
info "make defconfig (${board}, ${profile})"
configure_tree "${tree}" "${wanted}"

diffconfig="${out}/diffconfig-${profile}"
(cd "${tree}" && ./scripts/diffconfig.sh) >"${diffconfig}" 2>/dev/null || die "scripts/diffconfig.sh failed"
info "config ok; diffconfig in ${diffconfig}"
