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
	symlink "${REPO_DIR}/files" "${TREE}/files"
	mkdir -p "${TREE}/env" "${TREE}/tmp" "${WRT_WORKDIR}/out"
	symlink "${REPO_DIR}/config/kernel.config" "${TREE}/env/kernel-config"
	# The compiler caches live beside the tree, one per language, linked where
	# rules.mk, the feed's Go values and its Rust values look for them
	# (build-acceleration D6).
	cache="${WRT_WORKDIR}/compiler-cache"
	[ -L "${TREE}/tmp/go-build" ] || [ ! -e "${TREE}/tmp/go-build" ] ||
		die "${TREE}/tmp/go-build is a directory; move it to ${cache}/go-build"
	mkdir -p "${cache}/ccache" "${cache}/go-build" "${cache}/sccache"
	symlink "${cache}/ccache" "${TREE}/.ccache"
	symlink "${cache}/go-build" "${TREE}/tmp/go-build"
	symlink "${cache}/sccache" "${TREE}/.sccache"
	symlink "${REPO_DIR}/config/ccache.conf" "${cache}/ccache/ccache.conf"
)

# symlink <target> <link>: make <link> point to <target>, leaving a link that
# already does as it is. The kernel's configuration follows its inputs'
# times, a link's own among them (build-acceleration D4).
symlink() (
	current=$(readlink "$2") || current=
	[ "${current}" = "$1" ] || ln -sfn "$1" "$2"
)

# update_file <file>: write standard input to <file>, leaving a file that holds
# it already as it is, modification time included (build-acceleration D4).
update_file() (
	cat >"$1.new"
	if cmp -s "$1.new" "$1"; then
		rm -f "$1.new"
	else
		mv -f "$1.new" "$1"
	fi
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

# go_cache_entries: how many entries Go's build cache holds.
go_cache_entries() (
	[ -d "${TREE}/tmp/go-build/" ] || {
		echo 0
		return 0
	}
	find "${TREE}/tmp/go-build/" -type f -name '*-[ad]' | wc -l | tr -d ' '
)

# go_cache_compiled <start>: how many packages Go compiled since <start>,
# seconds since the epoch, instead of taking them from its build cache. Go keeps
# no statistics, but writes an action entry, its creation time inside, only for
# an action it ran. Those since <start> that hold an output count, but the index
# of a package's sources, which Go writes again for sources unpacked anew.
go_cache_compiled() (
	cache="${TREE}/tmp/go-build"
	[ -d "${cache}/" ] || {
		echo 0
		return 0
	}
	find "${cache}/" -type f -name '*-a' -newermt "@$1" \
		-exec awk -v start="$1" '$5 / 1e9 >= start && $4 > 0 { print $3 }' {} + |
		while read -r output; do
			head -c 8 "${cache}/$(printf %.2s "${output}")/${output}-d" 2>/dev/null |
				grep -qx 'go index' || echo "${output}"
		done | wc -l | tr -d ' '
)

# compiler_cache_start: zero ccache's statistics and start sccache's server
# anew, so that the report counts this build alone; print the time, seconds
# since the epoch, for compiler_cache_report and compiler_cache_trim. The server
# would exit after ten idle minutes, taking its statistics with it, and a build
# may reach its Rust packages long after it starts: this one runs until
# compiler_cache_report stops it.
compiler_cache_start() (
	ccache_run --zero-stats >/dev/null
	export SCCACHE_IDLE_TIMEOUT=0
	sccache_run --stop-server >/dev/null 2>&1 || true
	sccache_run --start-server >/dev/null 2>&1 || true
	date +%s
)

# compiler_cache_report <start>: what every compiler cache did in the build
# begun at <start>; then stop sccache's server, which outlives the build otherwise.
compiler_cache_report() (
	ccache_run --show-stats --verbose
	sccache_run --show-stats 2>/dev/null || true
	compiled=$(go_cache_compiled "$1")
	entries=$(go_cache_entries)
	info "Go build cache: ${compiled} packages compiled anew, ${entries} entries"
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
	update_file "${TREE}/env/wrt-boards.mk" <<-EOF
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

# The UB-indicative warning options, without their -W (spec quality/undefined-behavior).
UB_WARNINGS='aggressive-loop-optimizations array-bounds stringop-overflow
stringop-overread use-after-free dangling-pointer free-nonheap-object uninitialized
maybe-uninitialized shift-count-overflow shift-count-negative shift-negative-value
strict-aliasing address-of-packed-member'

# ub_warnings <log>: the UB-indicative warnings in a build log, one per line:
# option, file, function and line, tab-separated (toolchain-o3 D4). A warning falls
# in the function GCC names before it, if in the same file, else in none ("At top
# level" or another compilation). Inlined code is placed where GCC says it was
# inlined last: the outermost function and its call. Paths lose the build's
# directories (a build variant's also the versioned one inside), so the warnings
# of every board, checkout and version read alike.
ub_warnings() (
	# Bytes in every awk: GCC quotes in UTF-8 in a UTF-8 locale.
	LC_ALL=C UB_WARNINGS="${UB_WARNINGS}" awk '
		function strip(path) {
			if (sub(/^.*\/build_dir\/[^\/]+\/[^\/]+\//, "", path))
				sub(/^[^\/]*-[0-9][^\/]*\//, "", path)
			sub(/^.*\/staging_dir\/[^\/]+\//, "", path)
			while (sub(/^\.\.?\//, "", path)) {}
			return path
		}
		function quoted(text) {
			text = substr(text, index(text, "'\''") + 1)
			return substr(text, 1, index(text, "'\''") - 1)
		}
		BEGIN {
			n = split(ENVIRON["UB_WARNINGS"], list)
			for (i = 1; i <= n; i++) ub[list[i]] = 1
		}
		{ gsub(/\342\200\230|\342\200\231/, "'\''") }
		/^[^ :]+: (In|At) .*:$/ {
			context = substr($0, 1, index($0, ": ") - 1)
			if (index($0, "'\''")) function_ = quoted($0)
			else if ($0 ~ /: At /) function_ = ""
			else { function_ = substr($0, index($0, ": In ") + 5); sub(/:$/, "", function_) }
			next
		}
		/^([^ :]+: )?In [^'\'']*'\''.*'\'',$/ { inlined = quoted($0); at = ""; next }
		/^ +inlined from '\''.*'\'' at [^ ]+[,:]$/ {
			inlined = quoted($0)
			at = substr($0, index($0, "'\'' at ") + 5)
			next
		}
		/^[^ :]+:[0-9]+(:[0-9]+)?: (warning|error): / {
			chain = inlined; call = at; inlined = ""; at = ""
			if ($0 !~ /: warning: / || !match($0, /\[-W[a-z0-9-]+=?\]$/)) next
			option = substr($0, RSTART + 3, RLENGTH - 4)
			sub(/=$/, "", option)
			if (!(option in ub)) next
			split(call != "" ? call : $0, location, ":")
			if (chain != "") { context = location[1]; function_ = chain }
			print "-W" option "\t" strip(location[1]) "\t" \
				(location[1] == context ? function_ : "") "\t" location[2] | "LC_ALL=C sort -u"
		}
		END { close("LC_ALL=C sort -u") }
	' "$1"
)

# image_logs <manifest> <packageinfo>: the source package and the build log
# directory (under logs/) of every package of an image's manifest, from OpenWrt's
# package metadata (tmp/.packageinfo): the directory of the package's Makefile, and
# below it its build variant's. A package of no variant is built in every variant
# build of its source, that is in those of the image's other packages from it. The
# kernel is the target's, built with flags of its own, and has no package metadata.
image_logs() (
	awk '
		FNR == NR { if ($2 == "-" && $1 != "kernel") wanted[$1] = 1; next }
		function found() {
			if ((name abi) in wanted) {
				shipped[name abi] = dir
				if (variant != "") { variants[dir] = variants[dir] " " variant; of[name abi] = variant }
			}
			name = ""
		}
		/^Source-Makefile: / { found(); dir = $2; sub(/\/Makefile$/, "", dir); next }
		/^Package: / { found(); name = $2; abi = ""; variant = ""; next }
		/^ABI-Version: / { abi = $2; next }
		/^Build-Variant: / { variant = $2; next }
		END {
			found()
			for (package in wanted) {
				if (!(package in shipped)) {
					print "no package metadata for " package > "/dev/stderr"
					failed = 1
					continue
				}
				dir = shipped[package]
				source = dir
				sub(/.*\//, "", source)
				n = split(package in of ? of[package] : variants[dir], list)
				if (n == 0) print source "\t" dir | "LC_ALL=C sort -u"
				for (i = 1; i <= n; i++) print source "\t" dir "/" list[i] | "LC_ALL=C sort -u"
			}
			close("LC_ALL=C sort -u")
			exit failed
		}
	' "$1" "$2"
)

# warnings_harvest <logs> <records> <since>: record the UB-indicative warnings of
# every package's build log written since the file <since>, in <records> under the
# log's path. OpenWrt rewrites the logs of all packages whenever it runs their
# compile steps, also of those it finds up to date: such a log holds nothing but
# make's time line, and leaves the package's record of its last build standing.
warnings_harvest() (
	find "$1/package" -name compile.txt -newer "$3" | while IFS= read -r log; do
		grep -qv '^time: ' "${log}" || continue
		record="$2/${log#"$1"/}"
		mkdir -p "${record%/*}"
		ub_warnings "${log}" >"${record%.txt}.tsv"
	done
)

# image_warnings <manifest> <packageinfo> <records>: the recorded UB-indicative
# warnings of an image's packages, each led by its source package.
image_warnings() (
	logs=$(image_logs "$1" "$2") || exit
	printf '%s\n' "${logs}" | while IFS="$(printf '\t')" read -r source dir; do
		record="$3/${dir}/compile.tsv"
		[ -f "${record}" ] ||
			die "no record of ${dir}'s warnings; build it again: make ${dir}/{clean,compile}"
		awk -v source="${source}" '{ print source "\t" $0 }' "${record}"
	done
)

# profile_seeds <profile>: the seeds of a profile (config/profiles), in order. Those
# after a "|" apply to a board's configuration only, never to the board-neutral one
# the toolchain is built from (toolchain-o3 D5).
profile_seeds() (
	awk -v p="$1" -F: '
		/^[[:space:]]*(#|$)/ { next }
		$1 == p { print $2; found = 1 }
		END { if (!found) exit 1 }
	' "${REPO_DIR}/config/profiles" || die "unknown profile '$1' (see config/profiles)"
)

# build_name <board> <profile>: the name of a board's build directories and
# binaries (CONFIG_BUILD_SUFFIX): the board's, and after it the profile's for a
# profile with board-only seeds, whose objects differ from every other profile's.
build_name() (
	seeds=$(profile_seeds "$2") || exit
	case "${seeds}" in
		*"|"*) echo "$1_$2" ;;
		*) echo "$1" ;;
	esac
)

# merge_seeds <file>...: the lines of the seed files in order, each option only in
# the last line that sets it (CONFIG_X=..., or "# CONFIG_X is not set"), where
# that line stands: a later seed's line replaces an earlier one, and the
# composition holds one line per option. Comments and blank lines stay.
merge_seeds() (
	awk '
		function option(text) {
			if (text ~ /^CONFIG_[^= ]+=/) { sub(/=.*/, "", text); return text }
			if (text ~ /^# CONFIG_[^ ]+ is not set$/) { split(text, word, " "); return word[2] }
			return ""
		}
		{ line[NR] = $0; name = option($0); if (name != "") last[name] = NR }
		END {
			for (i = 1; i <= NR; i++) {
				name = option(line[i])
				if (name == "" || last[name] == i) print line[i]
			}
		}
	' "$@"
)

# compose_seeds <profile> <board> <output>: the profile's seed files in order
# (config/profiles), merged one line per option, then the board's seed
# (board-model D2): its device, its -mcpu after the profile's optimization flags,
# and build and output directories of its own (build_name). Without a board (an
# empty <board>), the configuration is the board-neutral one the host tools and
# the toolchain are built from: the seeds before any "|", every board's device,
# none of their CPU tuning, and no other device, which buildbot mode would
# otherwise add.
compose_seeds() (
	profile=$1
	board=$2
	output=$3
	seeds=$(profile_seeds "${profile}") || exit
	if [ -z "${board}" ]; then
		seeds=${seeds%%|*}
	else
		seeds=$(printf '%s\n' "${seeds}" | tr '|' ' ')
	fi
	set --
	for seed in ${seeds}; do
		file="${REPO_DIR}/config/${seed}.seed"
		[ -f "${file}" ] || die "missing seed file config/${seed}.seed"
		set -- "$@" "${file}"
	done
	merged=$(merge_seeds "$@")
	if [ -z "${board}" ]; then
		ids=$(board_ids)
		{
			printf '%s\n' "${merged}"
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
	name=$(build_name "${board}" "${profile}") || exit
	extra=$(printf '%s\n' "${merged}" | sed -n 's/^CONFIG_EXTRA_OPTIMIZATION="\(.*\)"$/\1/p')
	{
		printf '%s\n' "${merged}" | grep -v '^CONFIG_EXTRA_OPTIMIZATION='
		cat <<-EOF
			# The board: boards/${board}.json (board-model D2).
			CONFIG_TARGET_rockchip_armv8_DEVICE_${device}=y
			CONFIG_EXTRA_OPTIMIZATION="${extra:+${extra} }-mcpu=${cpu}"
			CONFIG_BUILD_SUFFIX="${name}"
			CONFIG_BINARY_FOLDER="${TREE}/bin/${name}"
		EOF
	} >"${output}"
)

# configure_tree <seed file>: the tree's .config from the seeds. Fails if make
# defconfig dropped or changed any of their lines (renamed or removed options,
# unmet dependencies). A configuration the same as the one its build
# directories were last configured with keeps that one's time
# (tmp/wrt-config-<build>, the build being host or the build directories'
# suffix): the kernel's configuration follows .config's time, and every kernel
# module follows the kernel's (build-acceleration D4).
configure_tree() (
	cp "$1" "${TREE}/.config"
	make -C "${TREE}" defconfig >/dev/null
	missing=$(missing_config_lines "$1" "${TREE}/.config")
	if [ -n "${missing}" ]; then
		printf 'error: defconfig dropped or changed these seed lines:\n%s\n' "${missing}" >&2
		exit 1
	fi
	suffix=$(sed -n 's/^CONFIG_BUILD_SUFFIX="\(.*\)"$/\1/p' "${TREE}/.config")
	last="${TREE}/tmp/wrt-config-${suffix:-host}"
	if cmp -s "${TREE}/.config" "${last}"; then
		touch -r "${last}" "${TREE}/.config"
	else
		cp -p "${TREE}/.config" "${last}"
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
# go, such as a patch a package would apply, but version.date, which patch.sh
# keeps; ignored build output stays.
move_tree() (
	git -C "$1" update-index -q --refresh >/dev/null || true
	git -C "$1" -c advice.detachedHead=false checkout -q -f --detach "$2"
	git -C "$1" clean -q -f -d -e /version.date
	head=$(git -C "$1" rev-parse HEAD)
	wanted=$(git -C "$1" rev-parse "$2^{commit}")
	[ "${head}" = "${wanted}" ] || die "$1 is not at $2"
)
