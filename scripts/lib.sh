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
	mkdir -p "${TREE}/env" "${TREE}/tmp" "${WRT_WORKDIR}/out"
	ln -sfn "${REPO_DIR}/config/kernel.config" "${TREE}/env/kernel-config"
	# The compiler caches live beside the tree, one per language, linked where
	# rules.mk, the feed's Go values and its Rust values look for them
	# (build-acceleration D6).
	cache="${WRT_WORKDIR}/compiler-cache"
	[ -L "${TREE}/tmp/go-build" ] || [ ! -e "${TREE}/tmp/go-build" ] ||
		die "${TREE}/tmp/go-build is a directory; move it to ${cache}/go-build"
	mkdir -p "${cache}/ccache" "${cache}/go-build" "${cache}/sccache"
	ln -sfn "${cache}/ccache" "${TREE}/.ccache"
	ln -sfn "${cache}/go-build" "${TREE}/tmp/go-build"
	ln -sfn "${cache}/sccache" "${TREE}/.sccache"
	ln -sfn "${REPO_DIR}/config/ccache.conf" "${cache}/ccache/ccache.conf"
)

# ccache_run <args>: the ccache that OpenWrt builds (tools/ccache), on the cache
# the tree links to. OpenWrt prints the cache's statistics after a build itself,
# but only into its silenced output.
ccache_run() (
	grep -qx 'CONFIG_CCACHE=y' "${TREE}/.config" || return 0
	ccache="${TREE}/staging_dir/host/bin/ccache"
	[ -x "${ccache}" ] || return 0
	CCACHE_DIR="${TREE}/.ccache" "${ccache}" "$@"
)

# sccache_run <args>: sccache, on the cache the tree links to, when Rust packages
# use it (CONFIG_RUST_SCCACHE).
sccache_run() (
	grep -qx 'CONFIG_RUST_SCCACHE=y' "${TREE}/.config" || return 0
	command -v sccache >/dev/null || return 0
	SCCACHE_DIR="${TREE}/.sccache" sccache "$@"
)

# go_cache_entries: how many entries Go's build cache holds. Go keeps no
# statistics: a build that adds no entry was served from the cache.
go_cache_entries() (
	[ -d "${TREE}/tmp/go-build/" ] || {
		echo 0
		return 0
	}
	find "${TREE}/tmp/go-build/" -type f -name '*-[ad]' | wc -l | tr -d ' '
)

# compiler_cache_start: zero ccache's and sccache's statistics, so that the
# report counts this build alone, and print Go's entry count for it.
compiler_cache_start() (
	ccache_run --zero-stats >/dev/null
	sccache_run --zero-stats >/dev/null 2>&1 || true
	go_cache_entries
)

# compiler_cache_report <Go entries at the start>: what every compiler cache did
# in this build; then stop sccache's server, which outlives the build otherwise.
compiler_cache_report() (
	ccache_run --show-stats --verbose
	sccache_run --show-stats 2>/dev/null || true
	after=$(go_cache_entries)
	info "Go build cache: $1 entries before the build, ${after} after"
	sccache_run --stop-server >/dev/null 2>&1 || true
)

# compiler_cache_trim <start>: drop from every compiler cache what a build begun at
# <start>, seconds since the epoch, did not use (CI, where each stage keeps a cache
# of its own): ccache by its record of each entry's last use, Go's cache and
# sccache's by modification time, which both refresh on use. sccache refreshes
# an entry on every hit, Go only one more than an hour old, so Go's cache keeps
# the hour before the build as well.
compiler_cache_trim() (
	now=$(date +%s)
	ccache_run --evict-older-than "$((now - $1 + 1))s"
	trim_unused "${TREE}/tmp/go-build" "$(($1 - 3600))"
	trim_unused "${TREE}/.sccache" "$1"
)

# trim_unused <directory> <time>: remove the files of <directory> not modified
# after <time>, seconds since the epoch.
trim_unused() (
	[ -d "$1/" ] || return 0
	find "$1/" -type f ! -newermt "@$2" -delete
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

# toolchain_stages <time log>: the stages of a build's time log that built part of
# the toolchain (tools, the cross toolchain, Go or Rust), which only toolchain-build
# builds (build-acceleration D7), one per line.
toolchain_stages() (
	awk -F '\t' '$2 == "begin" && ($4 ~ /^(tools|toolchain)\// ||
		$4 ~ /^package\/feeds\/packages\/(golang|golang-bootstrap|golang1\.[0-9]+|rust)$/) {
		print $4 " [" $3 "]"
	}' "$1" | LC_ALL=C sort -u
)

# toolchain_rust_std: the hash of the Rust standard libraries in
# staging_dir/hostpkg, the target's among them, or nothing when Rust is not
# built (build-acceleration D7): a rebuild changes it, as it does libc.so. Rust's
# uninstaller leaves its directories, so it is the libraries that count.
toolchain_rust_std() (
	rustlib="${TREE}/staging_dir/hostpkg/lib/rustlib"
	[ -d "${rustlib}" ] || return 0
	cd "${rustlib}" || return
	rlibs=$(find . -path './*/lib/*.rlib' -type f | LC_ALL=C sort)
	[ -n "${rlibs}" ] || return 0
	sum=$(printf '%s\n' "${rlibs}" | xargs sha256sum | sha256sum)
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
	[ -f "${TREE}/scripts/build-time-report.pl" ] || return 0
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

# fetch_locked <name> <dir>: make the pinned commit of <name> available in <dir>,
# shallow-fetched once, and check it out when <dir> is a new tree. An existing
# tree stays where it is, for patch_tree to move (build-acceleration D5).
fetch_locked() (
	dir=$2
	url=$(lock_field "$1" url)
	sha=$(lock_field "$1" sha)
	if [ ! -d "${dir}/.git" ]; then
		mkdir -p "${dir}"
		git -C "${dir}" init -q
		git -C "${dir}" remote add origin "${url}"
	fi
	git -C "${dir}" remote set-url origin "${url}"
	if ! git -C "${dir}" cat-file -e "${sha}^{commit}" 2>/dev/null; then
		git -C "${dir}" fetch -q --depth 1 origin "${sha}"
	fi
	git -C "${dir}" rev-parse -q --verify HEAD >/dev/null || move_tree "${dir}" "${sha}"
)

# patch_tree <name> <dir>: put <dir> on the pinned commit of <name> with
# patches/<name>/*.patch applied (series_commit, then move_tree).
patch_tree() (
	sha=$(lock_field "$1" sha)
	commit=$(series_commit "${REPO_DIR}/patches/$1" "$2" "${sha}")
	move_tree "$2" "${commit}"
)

# series_commit <patch dir> <repository> <base>: print the commit of <base> with
# <patch dir>/*.patch applied in name order. It is made in the object database,
# on an index of its own, so the work tree stays as it is: what git am makes of
# the series, with each patch's author, its date for both dates, and a fixed
# committer, so the same series always gives the same commit. Dies naming the
# first patch that does not apply.
series_commit() (
	dir=$1 repository=$2 commit=$3
	scratch=$(mktemp -d "${TMPDIR:-/tmp}/wrt-series.XXXXXX")
	trap 'rm -rf "${scratch}"' EXIT
	export GIT_INDEX_FILE="${scratch}/index" \
		GIT_COMMITTER_NAME=wrt-build GIT_COMMITTER_EMAIL=wrt-build@localhost
	git -C "${repository}" read-tree "${commit}"
	for patch in "${dir}"/*.patch; do
		[ -e "${patch}" ] || continue
		name=${patch#"${REPO_DIR}/"}
		git -C "${repository}" mailinfo "${scratch}/message" "${scratch}/diff" \
			<"${patch}" >"${scratch}/info" || die "not a patch: ${name}"
		if ! git -C "${repository}" apply --cached "${scratch}/diff"; then
			die "patch does not apply: ${name}"
		fi
		tree=$(git -C "${repository}" write-tree)
		author=$(sed -n 's/^Author: //p' "${scratch}/info")
		email=$(sed -n 's/^Email: //p' "${scratch}/info")
		date=$(sed -n 's/^Date: //p' "${scratch}/info")
		subject=$(sed -n 's/^Subject: //p' "${scratch}/info")
		commit=$(
			{
				printf '%s\n\n' "${subject}"
				cat "${scratch}/message"
			} | git stripspace |
				GIT_AUTHOR_NAME=${author} GIT_AUTHOR_EMAIL=${email} \
					GIT_AUTHOR_DATE=${date} GIT_COMMITTER_DATE=${date} \
					git -C "${repository}" commit-tree "${tree}" -p "${commit}"
		)
		info "applied ${name}"
	done
	printf '%s\n' "${commit}"
)

# move_tree <repository> <commit>: put the work tree on <commit>, detached. git
# writes only the files whose content differs from the commit the tree was on,
# so every other file keeps its modification time, and make rebuilds only what
# changed (build-acceleration D5). A file whose time changed but not its content
# counts as unchanged too: the index is refreshed first, or checkout would take
# it for a local change and write it again. Untracked files that are not ignored
# go, but version.date, which patch.sh keeps; ignored build output stays.
move_tree() (
	git -C "$1" update-index -q --refresh >/dev/null || true
	git -C "$1" -c advice.detachedHead=false checkout -q -f --detach "$2"
	git -C "$1" clean -q -f -d -e /version.date
	head=$(git -C "$1" rev-parse HEAD)
	wanted=$(git -C "$1" rev-parse "$2^{commit}")
	[ "${head}" = "${wanted}" ] || die "$1 is not at $2"
)
