#!/bin/sh
# test: run the system tests against the emulator.
# Usage: scripts/test.sh [profile] [pytest args]   (a built profile; default dev)
# emu-prepare turns the profile's build outputs into the emulator's files; pytest
# then runs as root of a private user namespace with its own network (design D14),
# so nothing on the host changes and no real root is needed.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

profile=${1:-dev}

require_linux
require_workdir
ensure_fhs test "$@"
[ "$#" -eq 0 ] || shift

out="${WRT_WORKDIR}/out/${profile}"
set -- "$@" --junitxml "${REPO_DIR}/tests/.reports/emulation.xml"
[ -f "${out}/manifest.json" ] || die "no build outputs in ${out}; run 'just build ${profile}' first"

use_tests_venv
cd "${REPO_DIR}/tests"
uv sync --locked --quiet
LG_EMU_DIR=$(uv run --no-sync emu-prepare "${out}" "${WRT_WORKDIR}/emu")
export LG_EMU_DIR
info "emulator files in ${LG_EMU_DIR}"
exec unshare --user --map-root-user --net --mount --pid --mount-proc --fork -- \
	uv run --no-sync pytest --lg-env targets/emulation.yaml "$@"
