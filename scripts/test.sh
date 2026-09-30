#!/bin/sh
# test: run the system tests against the emulator.
# Usage: scripts/test.sh <board> [profile] [pytest args]   (a built board; default profile dev)
# emu-prepare turns the board's build outputs into the emulator's files and the
# labgrid description of its machine (board-model D7); pytest then runs as root of
# a private user namespace with its own network (design D14), so nothing on the
# host changes and no real root is needed. Its temporary files, disks and signed
# builds among them, go to $WRT_WORKDIR/test/<board>, which each run empties
# first: /tmp may be memory, and a run's files would stay there.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

board=${1:-}
profile=${2:-dev}

require_linux
require_workdir
ensure_fhs test "$@"
[ -n "${board}" ] || die "usage: test <board> [profile] [pytest args]"
board_field "${board}" .device >/dev/null
shift
[ "$#" -eq 0 ] || shift

out="${WRT_WORKDIR}/out/${board}/${profile}"
set -- "$@" --junitxml "${REPO_DIR}/tests/.reports/emulation.xml" \
	--basetemp "${WRT_WORKDIR}/test/${board}"
[ -f "${out}/manifest.json" ] || die "no build outputs in ${out}; run 'just build ${board} ${profile}' first"

mkdir -p "${WRT_WORKDIR}/test"
use_tests_venv
cd "${REPO_DIR}/tests"
uv sync --locked --quiet
LG_EMU_DIR=$(uv run --no-sync emu-prepare "${out}" "${WRT_WORKDIR}/emu")
export LG_EMU_DIR
info "emulator files in ${LG_EMU_DIR}"
exec unshare --user --map-root-user --net --mount --pid --mount-proc --fork -- \
	uv run --no-sync pytest --lg-env "${LG_EMU_DIR}/target.yaml" "$@"
