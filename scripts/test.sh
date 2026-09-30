#!/bin/sh
# test: run the system tests against the emulator.
# Usage: scripts/test.sh <board> [profile] [pytest args]   (a built board; default profile dev)
# emu-prepare turns the board's build outputs into the emulator's files and the
# labgrid description of its machine (board-model D7); pytest then runs as root of
# a private user namespace with its own network (design D14), so nothing on the
# host changes and no real root is needed. The emulator's files go to
# $WRT_TESTDIR/emu and pytest's own, disks and signed builds among them, to
# $WRT_TESTDIR/test/<board>, which each run empties first: /tmp may be memory,
# and a run's files would stay there. $WRT_TESTDIR is the work directory unless
# set: a disk slow to flush stalls the emulator (docs/dev-setup.md).
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
testdir=${WRT_TESTDIR:-${WRT_WORKDIR}}
set -- "$@" --junitxml "${REPO_DIR}/tests/.reports/emulation.xml" \
	--basetemp "${testdir}/test/${board}"
[ -f "${out}/manifest.json" ] || die "no build outputs in ${out}; run 'just build ${board} ${profile}' first"

mkdir -p "${testdir}/test"
use_tests_venv
cd "${REPO_DIR}/tests"
uv sync --locked --quiet
LG_EMU_DIR=$(uv run --no-sync emu-prepare "${out}" "${testdir}/emu")
export LG_EMU_DIR
info "emulator files in ${LG_EMU_DIR}"
# The description is joined to its option: pytest finds its rootdir, and so
# pytest.toml, before labgrid's options are known, and would take a separate
# value for a path to test, the ancestor of the tests that run with no paths.
exec unshare --user --map-root-user --net --mount --pid --mount-proc --fork -- \
	uv run --no-sync pytest --lg-env="${LG_EMU_DIR}/target.yaml" "$@"
