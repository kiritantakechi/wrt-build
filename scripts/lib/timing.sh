# timing: a build's time log, and the report of where its time went.
# Usage: use timing   (POSIX sh; sourced)
# shellcheck shell=sh
: "${REPO_DIR:?load scripts/lib/core.sh first}"

# time_log <tree> <build>: OpenWrt's build time log of a build in <tree>
# (BUILD_TIME_LOG), emptied: host, or the build directories' suffix. make
# records a begin and an end event there for every prepare, configure, compile
# and install stage it runs.
time_log() (
	[ -d "$1" ] || die "time_log: no build tree at $1"
	log="$1/logs/build-time-$2.tsv"
	mkdir -p "$1/logs"
	: >"${log}"
	printf '%s\n' "${log}"
)

# time_report <tree> <log>: the stages of a build that took the most time, each
# with its wall share (each second split among the stages running in it) and its
# solo time (the seconds it ran alone, which only a faster stage would shorten).
time_report() (
	[ -d "$1" ] || die "time_report: no build tree at $1"
	[ -s "$2" ] || return 0
	[ -f "$1/scripts/build-time-report.pl" ] || return 0
	info "build time (${2##*/})"
	perl "$1/scripts/build-time-report.pl" -n 15 "$2"
)
