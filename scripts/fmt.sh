#!/bin/sh
# fmt: format the files that have a formatter in design D12.
# Usage: scripts/fmt.sh [formatter...]   (all formatters when none is named)
# The writing counterpart of the format checks in scripts/check.sh, under the
# same names: shfmt, nixfmt and ruff-format.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

formatters='shfmt nixfmt ruff-format'
requested=$*
for name in ${requested}; do
	case " ${formatters} " in
		*" ${name} "*) ;;
		*) die "unknown formatter '${name}' (formatters: ${formatters})" ;;
	esac
done

if [ -e /etc/NIXOS ]; then
	ensure_fhs test "$@"
fi

use_tests_venv
cd "${REPO_DIR}"
files=$(repo_files)
shell_files=$(printf '%s\n' "${files}" | xargs shfmt -f)
nix_files=$(printf '%s\n' "${files}" | grep -E '\.nix$')

# format <name> <command...>: run a requested formatter.
format() {
	formatter=$1
	shift
	case " ${requested:-${formatter}} " in
		*" ${formatter} "*) "$@" ;;
		*) ;;
	esac
}

# shellcheck disable=SC2086 # file lists are newline-separated plain paths
{
	format shfmt shfmt -w ${shell_files}
	format nixfmt nixfmt ${nix_files}
	format ruff-format uv run --directory tests --locked ruff format
}
info "formatted"
