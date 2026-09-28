#!/bin/sh
# fmt: format every file that has a formatter in design D12.
# Usage: scripts/fmt.sh
# The writing counterpart of the format checks in scripts/check.sh.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

if [ -e /etc/NIXOS ]; then
	ensure_fhs test "$@"
fi

cd "${REPO_DIR}"
files=$(repo_files)
shell_files=$(printf '%s\n' "${files}" | xargs shfmt -f)
nix_files=$(printf '%s\n' "${files}" | grep -E '\.nix$')

# shellcheck disable=SC2086 # file lists are newline-separated plain paths
{
	shfmt -w ${shell_files}
	nixfmt ${nix_files}
}
if [ -f tests/pyproject.toml ]; then
	uv run --directory tests --locked ruff format
fi
info "formatted"
