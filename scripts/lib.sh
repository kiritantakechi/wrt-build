# lib: shared helpers for scripts/*.sh.
# Usage: . "$(dirname -- "$0")/lib.sh"   (POSIX sh; sourced, never executed)
# POSIX sh has no local variables. So the helpers that compute, print or write
# run in a subshell, ( ... ), and their variables never reach the caller's; only
# require_workdir (TREE), use_tests_venv and ensure_fhs change the caller.
# shellcheck shell=sh

REPO_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
LOCK_FILE="${REPO_DIR}/upstream.lock"
BOARDS_DIR="${REPO_DIR}/boards"

die() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

info() {
	printf '==> %s\n' "$*" >&2
}

# Fail before anything touches the filesystem when the host cannot build:
# BTF (pahole) and mold are unavailable on macOS hosts.
require_linux() (
	os=$(uname -s)
	[ "${os}" = Linux ] ||
		die "builds run only on Linux; use the OrbStack NixOS VM or CI (see docs/dev-setup.md)"
)

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

# kernel_dir <build dir>: the kernel build directory in a board's build directory
# (make val.BUILD_DIR); exactly one must exist.
kernel_dir() (
	set -- "$1"/linux-rockchip_armv8/linux-[0-9]*
	[ "$#" -eq 1 ] && [ -d "$1" ] ||
		die "expected one kernel build directory, found: $* (clean the old one)"
	printf '%s\n' "$1"
)

# link_tree: put what lives outside the tree where the build reads it (design
# D7): the rootfs overlay, the kernel configuration overlay and the compiler
# cache (files/, env/ and .ccache are all gitignored upstream). The cache reads
# its settings from config/ccache.conf.
link_tree() (
	ln -sfn "${REPO_DIR}/files" "${TREE}/files"
	mkdir -p "${TREE}/env" "${WRT_WORKDIR}/ccache" "${WRT_WORKDIR}/out"
	ln -sfn "${REPO_DIR}/config/kernel.config" "${TREE}/env/kernel-config"
	ln -sfn "${WRT_WORKDIR}/ccache" "${TREE}/.ccache"
	ln -sfn "${REPO_DIR}/config/ccache.conf" "${WRT_WORKDIR}/ccache/ccache.conf"
)

# write_board_table: each board's U-Boot variant, id and environment directory,
# and its device, for the A/B hooks of uboot-rockchip and of the image recipe
# (env/wrt-boards.mk, board-model D3 and D4).
write_board_table() (
	boards=
	devices=
	ids=$(board_ids)
	for board in ${ids}; do
		variant=$(board_field "${board}" .uboot.variant)
		env_dir=$(board_field "${board}" .uboot.env_dir)
		device=$(board_field "${board}" .device)
		boards="${boards:+${boards} }${variant}:${board}:${env_dir}"
		devices="${devices:+${devices} }${device}"
	done
	mkdir -p "${TREE}/env"
	cat >"${TREE}/env/wrt-boards.mk" <<-EOF
		# Written by scripts/lib.sh from boards/*.json (board-model D3, D4): the
		# U-Boot variant, id and environment directory, and the device of every board.
		WRT_AB_BOARDS := ${boards}
		WRT_AB_DEVICES := ${devices}
	EOF
)

# toolchain_libc <toolchain dir>: the hash of the toolchain's C library, or
# nothing when it has none (board-model D2: the record in wrt-toolchain.json
# names it).
toolchain_libc() (
	[ -f "$1/lib/libc.so" ] || return 0
	sum=$(sha256sum "$1/lib/libc.so")
	echo "${sum%% *}"
)

# time_log <build>: OpenWrt's build time log of a build (BUILD_TIME_LOG), emptied:
# host, or the build directories' suffix. make records a begin and an end event
# there for every prepare, configure, compile and install stage it runs.
time_log() (
	log="${TREE}/logs/build-time-$1.tsv"
	mkdir -p "${TREE}/logs"
	: >"${log}"
	printf '%s\n' "${log}"
)

# time_report <log>: the stages of a build that took the most time, each with its
# wall share (each second split among the stages running in it) and its solo
# time (the seconds it ran alone, which only a faster stage would shorten).
time_report() (
	[ -s "$1" ] || return 0
	info "build time (${1##*/})"
	perl "${TREE}/scripts/build-time-report.pl" -n 15 "$1"
)

# compose_seeds <profile> <board> <output>: the profile's seed files in order
# (config/profiles), then the board's seed (board-model D2): its device, its
# -mcpu after the profile's optimization flags, and build and output directories
# of its own. Without a board (an empty <board>), the configuration is the
# board-neutral one the host tools and the toolchain are built from: every
# board's device, none of their CPU tuning, and no other device, which buildbot
# mode would otherwise add.
compose_seeds() (
	seeds=$(awk -v p="$1" -F: '
		/^[[:space:]]*(#|$)/ { next }
		$1 == p { print $2; found = 1 }
		END { if (!found) exit 1 }
	' "${REPO_DIR}/config/profiles") || die "unknown profile '$1' (see config/profiles)"
	board=$2
	output=$3
	set --
	for seed in ${seeds}; do
		file="${REPO_DIR}/config/${seed}.seed"
		[ -f "${file}" ] || die "missing seed file config/${seed}.seed"
		set -- "$@" "${file}"
	done
	if [ -z "${board}" ]; then
		ids=$(board_ids)
		{
			cat "$@"
			cat <<-EOF
				# Every board, with none of their CPU tuning (board-model D2).
				CONFIG_TARGET_MULTI_PROFILE=y
				# CONFIG_TARGET_ALL_PROFILES is not set
				# CONFIG_TARGET_PER_DEVICE_ROOTFS is not set
			EOF
			for id in ${ids}; do
				device=$(board_field "${id}" .device)
				echo "CONFIG_TARGET_DEVICE_rockchip_armv8_DEVICE_${device}=y"
			done
		} >"${output}"
		return 0
	fi
	device=$(board_field "${board}" .device)
	cpu=$(board_field "${board}" .cpu)
	extra=$(sed -n 's/^CONFIG_EXTRA_OPTIMIZATION="\(.*\)"$/\1/p' "$@" | tail -n 1)
	{
		grep -hv '^CONFIG_EXTRA_OPTIMIZATION=' "$@"
		cat <<-EOF
			# The board: boards/${board}.json (board-model D2).
			CONFIG_TARGET_rockchip_armv8_DEVICE_${device}=y
			CONFIG_EXTRA_OPTIMIZATION="${extra:+${extra} }-mcpu=${cpu}"
			CONFIG_BUILD_SUFFIX="${board}"
			CONFIG_BINARY_FOLDER="${TREE}/bin/${board}"
		EOF
	} >"${output}"
)

# configure_tree <seed file>: the tree's .config from the seeds. Fails if make
# defconfig dropped or changed any of their lines (renamed or removed options,
# unmet dependencies).
configure_tree() (
	cp "$1" "${TREE}/.config"
	make -C "${TREE}" defconfig >/dev/null
	missing=$(missing_config_lines "$1" "${TREE}/.config")
	if [ -n "${missing}" ]; then
		printf 'error: defconfig dropped or changed these seed lines:\n%s\n' "${missing}" >&2
		exit 1
	fi
)

# missing_config_lines <wanted> <actual>: print each option line of <wanted>
# (CONFIG_X=... or "# CONFIG_X is not set") that <actual> lacks verbatim. Symbols
# may hold any character but "=" and blanks: packages' hold "-", "." and "+".
missing_config_lines() (
	grep -E '^(CONFIG_[^=[:space:]]+=|# CONFIG_[^[:space:]]+ is not set$)' "$1" |
		while IFS= read -r line; do
			grep -Fxq -- "${line}" "$2" || printf '  %s\n' "${line}"
		done
)

# board_ids: the ids of the supported boards (boards/<id>.json), one per line.
board_ids() (
	for description in "${BOARDS_DIR}"/*.json; do
		[ -e "${description}" ] || continue
		name=${description##*/}
		printf '%s\n' "${name%.json}"
	done
)

# board_field <board> <jq filter>: a fact of a board's description. Dies on an
# unknown board, naming the known ones, and on a fact the description lacks.
board_field() (
	description="${BOARDS_DIR}/$1.json"
	if [ ! -f "${description}" ]; then
		known=$(board_ids | tr '\n' ' ')
		die "no board '$1' (boards: ${known% })"
	fi
	jq -er "$2" "${description}" || die "boards/$1.json has no $2"
)

# lock_field <name> <field>: field is url, sha or epoch.
lock_field() (
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
)

# lock_feeds: feed names in lock order (everything except openwrt itself).
lock_feeds() (
	awk '/^[[:space:]]*(#|$)/ { next } $1 != "openwrt" { print $1 }' "${LOCK_FILE}"
)

# checkout_locked <name> <dir>: put <dir> on the pinned commit of <name>.
checkout_locked() (
	url=$(lock_field "$1" url)
	sha=$(lock_field "$1" sha)
	git_checkout_sha "$2" "${url}" "${sha}"
)

# reset_to_lock: put the openwrt tree and every feed back on its pinned commit
# (dropping applied patches) and restore version.date, which git clean removes.
reset_to_lock() (
	checkout_locked openwrt "${TREE}"
	# Build timestamp comes from the pinned commit, not from when patches were
	# applied (scripts/get_source_date_epoch.sh reads version.date first).
	lock_field openwrt epoch >"${TREE}/version.date"
	feeds=$(lock_feeds)
	for feed in ${feeds}; do
		checkout_locked "${feed}" "${TREE}/feeds/${feed}"
	done
)

# git_checkout_sha <dir> <url> <sha>: shallow-fetch exactly <sha> and check it out
# detached, discarding local commits (e.g. previously applied patches).
git_checkout_sha() (
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
)
