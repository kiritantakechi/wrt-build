# core: what every script needs: the repository's place, messages, the guards of
# the host and the environment, the build tree, and use, which loads the other
# library modules.
# Usage: . "$(dirname -- "$0")/lib/core.sh", then use <module>...   (POSIX sh; sourced)
# POSIX sh has no local variables. So the functions that compute, print or write
# run in a subshell, ( ... ), and their variables never reach the caller's; only
# use, ensure_fhs and use_tests_venv change the caller, as their names say.
# shellcheck shell=sh

REPO_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)

die() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

info() {
	printf '==> %s\n' "$*" >&2
}

# use <module>...: load each library module (scripts/lib/<module>.sh) once; a
# module loads what it depends on itself.
use() {
	for lib_module in "$@"; do
		case " ${LIB_MODULES:-} " in
			*" ${lib_module} "*) ;;
			*)
				[ -f "${REPO_DIR}/scripts/lib/${lib_module}.sh" ] || die "no library module '${lib_module}'"
				LIB_MODULES="${LIB_MODULES:+${LIB_MODULES} }${lib_module}"
				# shellcheck source=/dev/null # the module that use names
				. "${REPO_DIR}/scripts/lib/${lib_module}.sh"
				;;
		esac
	done
}

# loaded_modules <script>...: the library modules the scripts load, with the
# modules those load in turn, core first; one file per line.
loaded_modules() (
	names=core
	todo=$(sed -n 's/^use //p' "$@")
	while [ -n "${todo}" ]; do
		next=
		for name in ${todo}; do
			case " ${names} " in
				*" ${name} "*) continue ;;
				*) ;;
			esac
			names="${names} ${name}"
			uses=$(sed -n 's/^use //p' "${REPO_DIR}/scripts/lib/${name}.sh")
			next="${next} ${uses}"
		done
		todo=${next}
	done
	for name in ${names}; do
		printf '%s\n' "${REPO_DIR}/scripts/lib/${name}.sh"
	done
)

# Fail before anything touches the filesystem when the host cannot build:
# BTF (pahole) and mold are unavailable on macOS hosts.
require_linux() (
	os=$(uname -s)
	[ "${os}" = Linux ] ||
		die "builds run only on Linux; use the OrbStack NixOS VM or CI (see docs/dev-setup.md)"
)

# workdir_tree: the build tree, in the work directory, which lives outside the
# repository (WRT_WORKDIR).
workdir_tree() (
	[ -n "${WRT_WORKDIR:-}" ] || die "WRT_WORKDIR is not set (see docs/dev-setup.md)"
	[ -d "${WRT_WORKDIR}" ] || die "WRT_WORKDIR does not exist: ${WRT_WORKDIR}"
	case "${WRT_WORKDIR}" in
		"${REPO_DIR}" | "${REPO_DIR}"/*) die "WRT_WORKDIR must be outside the repository" ;;
		*) ;;
	esac
	printf '%s\n' "${WRT_WORKDIR}/openwrt"
)

# ensure_fhs <build|test> [args]: re-execute the calling script inside the Nix FHS
# environment of that kind unless already there. The test environment is a
# superset of the build environment, so it satisfies both.
ensure_fhs() {
	kind=$1
	shift
	case "${WRT_FHS:-}:${kind}" in
		build:build | test:build | test:test) return 0 ;;
		build:test) die "inside wrt-build-fhs; run this from the 'nix develop' shell instead" ;;
		:build | :test) ;;
		*) die "ensure_fhs: unknown environment '${kind}'" ;;
	esac
	fhs="wrt-${kind}-fhs"
	command -v "${fhs}" >/dev/null 2>&1 ||
		die "${fhs} not found; run through 'nix develop' (see docs/dev-setup.md)"
	# shellcheck disable=SC2016 # expanded by the inner shell, not here
	exec "${fhs}" -c 'exec "$0" "$@"' "$0" "$@"
}

# repo_files: files of the repository (tracked and new, not ignored) that follow
# its code standards; upstream-format patches and generated tool files do not.
repo_files() (
	git -C "${REPO_DIR}" ls-files --cached --others --exclude-standard |
		grep -vE '^(patches|docs/upstream|\.claude)/' |
		while IFS= read -r file; do
			[ ! -e "${REPO_DIR}/${file}" ] || printf '%s\n' "${file}"
		done
)

# use_tests_venv: point uv at the tests' virtual environment for this OS and
# architecture. macOS and the Linux VM share the repository, and a virtual
# environment only works on the host that created it.
use_tests_venv() {
	host=$(uname -sm | tr 'A-Z ' 'a-z-')
	UV_PROJECT_ENVIRONMENT="${REPO_DIR}/tests/.venv-${host}"
	export UV_PROJECT_ENVIRONMENT
}
