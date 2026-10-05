#!/bin/sh
# compiler-cache-key: print a stage's compiler cache key and the prefix of its keys, as key=<value> and prefix=<value>.
# Usage: scripts/compiler-cache-key.sh <stage> >>"$GITHUB_OUTPUT"   (host, or a board)
# Each stage keeps one compiler cache (build-acceleration D6), keyed by the stage,
# whose packages no other stage compiles alike, then by the settings of
# config/ccache.conf, which decide whether a ccache entry can hit (it identifies
# the compiler by its content), then by the run. Its comments set nothing, so
# editing them keeps the caches. Go's and sccache's entries name their compiler
# themselves.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

stage=${1:-}

[ -n "${stage}" ] || die "usage: compiler-cache-key <stage>"
[ "${stage}" = host ] || board_field "${stage}" .device >/dev/null

settings=$(grep -Ev '^[[:space:]]*(#|$)' "${REPO_DIR}/config/ccache.conf" | sha256sum)
prefix="compiler-cache-${stage}-${settings%% *}-"
printf 'key=%s%s\nprefix=%s\n' "${prefix}" "${GITHUB_RUN_ID:-local}" "${prefix}"
