#!/bin/sh
# marks-check: check the packet marks the configuration templates use against config/marks.tsv.
# Usage: scripts/marks-check.sh [dir...]   (default: files feed)
# The table must not give one bit to two owners. A mark in a template of package
# <owner> (feed/*/<owner>/, or files/ for the image overlay) must lie within that
# owner's masks: a bit of another owner's mask is a conflict, a bit of no mask is
# unregistered (r4s-ebpf-datapath design D4).
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

[ "$#" -gt 0 ] || set -- "${REPO_DIR}/files" "${REPO_DIR}/feed"
status=0

# fail <message>: report a problem and carry on, so that one run shows them all.
fail() {
	printf '%s\n' "$*" >&2
	status=1
}

# owner_of <path>: the package a template belongs to.
owner_of() {
	case "$1" in
		*/feed/*/*/*)
			package=${1#*/feed/*/}
			echo "${package%%/*}"
			;;
		*) echo files ;;
	esac
}

# One "mask owner" per well-formed row of the table (four fields, the mask as 0x and
# eight hexadecimal digits), and one "path mark" per hexadecimal value on a template
# line that mentions a mark.
rows=$(awk -F'\t' '
	NR == 1 { next }
	NF == 4 && length($1) == 10 && $1 ~ /^0x[0-9a-f]+$/ { print $1, $2; next }
	{ printf "config/marks.tsv:%d: want mask, owner, purpose and source, the mask as 0x%%08x\n", NR > "/dev/stderr"; bad = 1 }
	END { exit bad }
' "${REPO_DIR}/config/marks.tsv") || status=1
marks=$(grep -rHoiE 'mark[^0-9]*0x[0-9a-f]+' "$@" |
	sed -E 's/^([^:]+):.*(0x[0-9a-fA-F]+)$/\1 \2/') || true

set -f
IFS='
'
seen=
for row in ${rows}; do
	for earlier in ${seen}; do
		[ "$((${row%% *} & ${earlier%% *}))" -eq 0 ] ||
			fail "config/marks.tsv: ${row%% *} (${row#* }) overlaps ${earlier%% *} (${earlier#* })"
	done
	seen="${seen}${row}${IFS}"
done

for found in ${marks}; do
	path=${found%% *}
	mark=${found#* }
	owner=$(owner_of "${path}")
	registered=0
	for row in ${rows}; do
		mask=${row%% *}
		[ "$((mark & mask))" -ne 0 ] || continue
		registered=$((registered | mask))
		[ "${row#* }" = "${owner}" ] ||
			fail "${path#"${REPO_DIR}"/}: mark ${mark} (${owner}) overlaps ${mask} (${row#* })"
	done
	[ "$((mark & ~registered))" -eq 0 ] ||
		fail "${path#"${REPO_DIR}"/}: mark ${mark} (${owner}) is not in config/marks.tsv"
done

exit "${status}"
