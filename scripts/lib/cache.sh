# cache: the compiler caches a build tree links to: ccache, sccache and Go's
# build cache (build-acceleration D6), their statistics and their trimming.
# Usage: use cache   (POSIX sh; sourced)
# shellcheck shell=sh
: "${REPO_DIR:?load scripts/lib/core.sh first}"

# ccache_run <tree> <args>: the ccache that OpenWrt builds (tools/ccache), on the
# cache the tree links to. OpenWrt prints the cache's statistics after a build
# itself, but only into its silenced output.
ccache_run() (
	[ -d "$1" ] || die "ccache_run: no build tree at $1"
	tree=$1
	shift
	grep -qx 'CONFIG_CCACHE=y' "${tree}/.config" || return 0
	ccache="${tree}/staging_dir/host/bin/ccache"
	[ -x "${ccache}" ] || return 0
	CCACHE_DIR="${tree}/.ccache" "${ccache}" "$@"
)

# sccache_run <tree> <args>: sccache, on the cache the tree links to, when Rust
# packages use it (CONFIG_RUST_SCCACHE).
sccache_run() (
	[ -d "$1" ] || die "sccache_run: no build tree at $1"
	tree=$1
	shift
	grep -qx 'CONFIG_RUST_SCCACHE=y' "${tree}/.config" || return 0
	command -v sccache >/dev/null || return 0
	SCCACHE_DIR="${tree}/.sccache" sccache "$@"
)

# go_cache_entries <tree>: how many entries Go's build cache holds.
go_cache_entries() (
	[ -d "$1" ] || die "go_cache_entries: no build tree at $1"
	[ -d "$1/tmp/go-build/" ] || {
		echo 0
		return 0
	}
	find "$1/tmp/go-build/" -type f -name '*-[ad]' | wc -l | tr -d ' '
)

# go_cache_compiled <tree> <start>: how many packages Go compiled since <start>,
# seconds since the epoch, instead of taking them from its build cache. Go keeps
# no statistics, but writes an action entry, its creation time inside, only for
# an action it ran. Those since <start> that hold an output count, but the index
# of a package's sources, which Go writes again for sources unpacked anew.
go_cache_compiled() (
	[ -d "$1" ] || die "go_cache_compiled: no build tree at $1"
	cache="$1/tmp/go-build"
	[ -d "${cache}/" ] || {
		echo 0
		return 0
	}
	find "${cache}/" -type f -name '*-a' -newermt "@$2" \
		-exec awk -v start="$2" '$5 / 1e9 >= start && $4 > 0 { print $3 }' {} + |
		while read -r output; do
			head -c 8 "${cache}/$(printf %.2s "${output}")/${output}-d" 2>/dev/null |
				grep -qx 'go index' || echo "${output}"
		done | wc -l | tr -d ' '
)

# trim_unused <directory> <time>: remove the files of <directory> not modified
# after <time>, seconds since the epoch.
trim_unused() (
	[ -d "$1/" ] || return 0
	find "$1/" -type f ! -newermt "@$2" -delete
)

# compiler_cache_start <tree>: zero ccache's statistics and start sccache's
# server anew, so that the report counts this build alone; print the time,
# seconds since the epoch, for compiler_cache_report and compiler_cache_trim. The
# server would exit after ten idle minutes, taking its statistics with it, and a
# build may reach its Rust packages long after it starts: this one runs until
# compiler_cache_report stops it.
compiler_cache_start() (
	[ -d "$1" ] || die "compiler_cache_start: no build tree at $1"
	ccache_run "$1" --zero-stats >/dev/null
	export SCCACHE_IDLE_TIMEOUT=0
	sccache_run "$1" --stop-server >/dev/null 2>&1 || true
	sccache_run "$1" --start-server >/dev/null 2>&1 || true
	date +%s
)

# compiler_cache_report <tree> <start>: what every compiler cache did in the
# build begun at <start>; then stop sccache's server, which outlives the build
# otherwise.
compiler_cache_report() (
	[ -d "$1" ] || die "compiler_cache_report: no build tree at $1"
	ccache_run "$1" --show-stats --verbose
	sccache_run "$1" --show-stats 2>/dev/null || true
	compiled=$(go_cache_compiled "$1" "$2")
	entries=$(go_cache_entries "$1")
	info "Go build cache: ${compiled} packages compiled anew, ${entries} entries"
	sccache_run "$1" --stop-server >/dev/null 2>&1 || true
)

# compiler_cache_trim <tree> <start>: drop from every compiler cache what a build
# begun at <start>, seconds since the epoch, did not use (CI, where each stage
# keeps a cache of its own): ccache by its record of each entry's last use, Go's
# cache and sccache's by modification time, which both refresh on use. sccache
# refreshes an entry on every hit, Go only one more than an hour old, so Go's
# cache keeps the hour before the build as well.
compiler_cache_trim() (
	[ -d "$1" ] || die "compiler_cache_trim: no build tree at $1"
	now=$(date +%s)
	ccache_run "$1" --evict-older-than "$((now - $2 + 1))s"
	trim_unused "$1/tmp/go-build" "$(($2 - 3600))"
	trim_unused "$1/.sccache" "$2"
)
