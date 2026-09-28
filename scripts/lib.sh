# lib: shared helpers for scripts/*.sh.
# Usage: . "$(dirname -- "$0")/lib.sh"   (POSIX sh; sourced, never executed)
# shellcheck shell=sh

REPO_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
LOCK_FILE="${REPO_DIR}/upstream.lock"

die() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

info() {
	printf '==> %s\n' "$*" >&2
}

# Fail before anything touches the filesystem when the host cannot build:
# BTF (pahole) and mold are unavailable on macOS hosts.
require_linux() {
	os=$(uname -s)
	[ "${os}" = Linux ] ||
		die "builds run only on Linux; use the OrbStack NixOS VM or CI (see docs/dev-setup.md)"
}

# The build tree lives outside the repository.
require_workdir() {
	[ -n "${WRT_WORKDIR:-}" ] || die "WRT_WORKDIR is not set (see docs/dev-setup.md)"
	[ -d "${WRT_WORKDIR}" ] || die "WRT_WORKDIR does not exist: ${WRT_WORKDIR}"
	case "${WRT_WORKDIR}" in
		"${REPO_DIR}" | "${REPO_DIR}"/*) die "WRT_WORKDIR must be outside the repository" ;;
		*) ;;
	esac
	TREE="${WRT_WORKDIR}/openwrt"
}

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
repo_files() {
	git -C "${REPO_DIR}" ls-files --cached --others --exclude-standard |
		grep -vE '^(patches|docs/upstream|\.claude)/' |
		while IFS= read -r file; do
			[ ! -e "${REPO_DIR}/${file}" ] || printf '%s\n' "${file}"
		done
}

# use_tests_venv: point uv at the tests' virtual environment for this OS and
# architecture. macOS and the Linux VM share the repository, and a virtual
# environment only works on the host that created it.
use_tests_venv() {
	host=$(uname -sm | tr 'A-Z ' 'a-z-')
	UV_PROJECT_ENVIRONMENT="${REPO_DIR}/tests/.venv-${host}"
	export UV_PROJECT_ENVIRONMENT
}

# kernel_dir: the kernel build directory of the tree; exactly one must exist.
kernel_dir() {
	set -- "${TREE}"/build_dir/target-*/linux-rockchip_armv8/linux-[0-9]*
	[ "$#" -eq 1 ] && [ -d "$1" ] ||
		die "expected one kernel build directory, found: $* (clean the old one)"
	printf '%s\n' "$1"
}

# missing_config_lines <wanted> <actual>: print each option line of <wanted>
# (CONFIG_X=... or "# CONFIG_X is not set") that <actual> lacks verbatim.
missing_config_lines() {
	grep -E '^(CONFIG_[A-Za-z0-9_]+=|# CONFIG_[A-Za-z0-9_]+ is not set$)' "$1" |
		while IFS= read -r line; do
			grep -Fxq -- "${line}" "$2" || printf '  %s\n' "${line}"
		done
}

# lock_field <name> <field>: field is url, sha or epoch.
lock_field() {
	awk -v name="$1" -v field="$2" '
		/^[[:space:]]*(#|$)/ { next }
		$1 == name {
			if (field == "url") print $2
			else if (field == "sha") print $3
			else if (field == "epoch") print $4
			found = 1
		}
		END { if (!found) exit 1 }
	' "${LOCK_FILE}" || die "upstream.lock has no entry for '$1'"
}

# lock_feeds: feed names in lock order (everything except openwrt itself).
lock_feeds() {
	awk '/^[[:space:]]*(#|$)/ { next } $1 != "openwrt" { print $1 }' "${LOCK_FILE}"
}

# checkout_locked <name> <dir>: put <dir> on the pinned commit of <name>.
checkout_locked() {
	url=$(lock_field "$1" url)
	sha=$(lock_field "$1" sha)
	git_checkout_sha "$2" "${url}" "${sha}"
}

# reset_to_lock: put the openwrt tree and every feed back on its pinned commit
# (dropping applied patches) and restore version.date, which git clean removes.
reset_to_lock() {
	checkout_locked openwrt "${TREE}"
	# Build timestamp comes from the pinned commit, not from when patches were
	# applied (scripts/get_source_date_epoch.sh reads version.date first).
	lock_field openwrt epoch >"${TREE}/version.date"
	feeds=$(lock_feeds)
	for feed in ${feeds}; do
		checkout_locked "${feed}" "${TREE}/feeds/${feed}"
	done
}

# git_checkout_sha <dir> <url> <sha>: shallow-fetch exactly <sha> and check it out
# detached, discarding local commits (e.g. previously applied patches).
git_checkout_sha() {
	dir=$1 url=$2 sha=$3
	if [ ! -d "${dir}/.git" ]; then
		mkdir -p "${dir}"
		git -C "${dir}" init -q
		git -C "${dir}" remote add origin "${url}"
	fi
	git -C "${dir}" remote set-url origin "${url}"
	if ! git -C "${dir}" cat-file -e "${sha}^{commit}" 2>/dev/null; then
		git -C "${dir}" fetch -q --depth 1 origin "${sha}"
	fi
	git -C "${dir}" -c advice.detachedHead=false checkout -q -f --detach "${sha}"
	# Files added by earlier patch runs are untracked now; drop them so git am can
	# re-add them. Ignored build output (dl/, build_dir/, feeds/, .config) is kept.
	git -C "${dir}" clean -q -f -d
	head=$(git -C "${dir}" rev-parse HEAD)
	[ "${head}" = "${sha}" ] || die "${dir} is not at ${sha}"
}
