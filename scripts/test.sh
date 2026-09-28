#!/bin/sh
# test: run the system tests against the emulator.
# Usage: scripts/test.sh [profile] [pytest args]   (a built profile; default dev)
# emu-prepare turns the profile's image into the emulator's files; pytest then
# runs as root of a private user namespace with its own network (design D14), so
# nothing on the host changes and no real root is needed.
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
images=$(find "${out}/targets" -maxdepth 1 -name '*-sysupgrade.img.gz' 2>/dev/null)
[ -n "${images}" ] || die "no sysupgrade image in ${out}/targets; run 'just build ${profile}' first"
count=$(printf '%s\n' "${images}" | wc -l)
[ "${count}" -eq 1 ] || die "more than one sysupgrade image in ${out}/targets"

use_tests_venv
cd "${REPO_DIR}/tests"
uv sync --locked --quiet
LG_EMU_DIR=$(uv run --no-sync emu-prepare --manifest "${out}/manifest.json" "${images}" "${WRT_WORKDIR}/emu")
LG_BOOTARGS=$(cat "${LG_EMU_DIR}/bootargs")
export LG_EMU_DIR LG_BOOTARGS
info "emulator files in ${LG_EMU_DIR}"
exec unshare --user --map-root-user --net --mount --pid --mount-proc --fork -- \
	uv run --no-sync pytest --lg-env targets/emulation.yaml --target-kind emulation "$@"
