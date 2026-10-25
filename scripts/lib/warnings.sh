# warnings: the UB-indicative warnings of a build: read from its logs, recorded
# per package, and gathered for an image's packages (toolchain-o3 D4).
# Usage: use warnings   (POSIX sh; sourced)
# shellcheck shell=sh
: "${REPO_DIR:?load scripts/lib/core.sh first}"

# The UB-indicative warning options, without their -W (spec quality/undefined-behavior).
UB_WARNINGS='aggressive-loop-optimizations array-bounds stringop-overflow
stringop-overread use-after-free dangling-pointer free-nonheap-object uninitialized
maybe-uninitialized shift-count-overflow shift-count-negative shift-negative-value
strict-aliasing address-of-packed-member'

# ub_warnings <log>: the UB-indicative warnings in a build log, one per line:
# option, file, function and line, tab-separated (ub-warnings.awk). A warning falls
# in the function GCC names before it, if in the same file, else in none ("At top
# level" or another compilation). Inlined code is placed where GCC says it was
# inlined last: the outermost function and its call, named as in the source,
# without the suffixes of GCC's clones. Paths lose the build's directories (a
# build variant's also the versioned one inside) and their ./ parts, so the
# warnings of every board, checkout, version and optimization read alike.
ub_warnings() (
	LC_ALL=C UB_WARNINGS="${UB_WARNINGS}" awk -f "${REPO_DIR}/scripts/lib/ub-warnings.awk" "$1"
)

# image_logs <manifest> <packageinfo>: the source package and the build log
# directory (under logs/) of every package of an image's manifest, from OpenWrt's
# package metadata (tmp/.packageinfo, image-logs.awk): the directory of the
# package's Makefile, and below it its build variant's. A package of no variant is
# built in every variant build of its source, that is in those of the image's
# other packages from it. The kernel is the target's, built with flags of its own,
# and has no package metadata.
image_logs() (
	awk -f "${REPO_DIR}/scripts/lib/image-logs.awk" "$1" "$2"
)

# warnings_harvest <logs> <records> <time_log>: record the UB-indicative warnings
# of every package the build compiled, as its time log names them (a compile
# stage, timing.sh), from its log, in <records> under the log's path. OpenWrt
# rewrites a package's log whenever it runs its compile step: also when it finds
# the package up to date, and when it only packs it again (its package missing
# from the output directory, or its packaging rules changed), which writes no
# compiler output. Only a compiled package's record changes; one that compiles
# without a word (base-files) gets an empty record.
warnings_harvest() (
	awk -F '\t' '$2 == "begin" && $3 == "compile" && $4 ~ /^package\// { print $4 }' "$3" |
		LC_ALL=C sort -u | while IFS= read -r package; do
		log="$1/${package}/compile.txt"
		[ -f "${log}" ] || die "no log of ${package}, which the build compiled"
		record="$2/${package}/compile.tsv"
		mkdir -p "${record%/*}"
		ub_warnings "${log}" >"${record}"
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
