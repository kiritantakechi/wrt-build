#!/bin/sh
# test-device: run the system tests against a real R4S.
# Usage: scripts/test-device.sh <host> [pytest args]   (the R4S's LAN address)
# The counterpart of test: same suite, same report format; tests marked for the
# emulator are skipped with their reason. Runs on Linux and macOS.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

host=${1:-}
[ -n "${host}" ] || die "usage: test-device <host> [pytest args]"

# NixOS cannot run the generic Linux binaries that uv installs.
if [ -e /etc/NIXOS ]; then
	ensure_fhs test "$@"
fi
shift
set -- "$@" --junitxml "${REPO_DIR}/tests/.reports/device.xml"

use_tests_venv
cd "${REPO_DIR}/tests"
uv sync --locked --quiet
LG_DEVICE_HOST=${host}
export LG_DEVICE_HOST
exec uv run --no-sync pytest --lg-env targets/r4s.yaml --target-kind device "$@"
