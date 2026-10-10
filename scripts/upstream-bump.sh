#!/bin/sh
# upstream-bump: move upstream.lock to the heads of the upstream branches (r4s-release-pipeline D5).
# Usage: scripts/upstream-bump.sh <description> [--lock <file>]
# For each repository of the lock (upstream.lock unless --lock), finds the head
# of its default branch and, when any moved, rewrites the lock (SHA and commit
# time of each) and writes the pull request to <description>: the title, a blank
# line, then the old and new SHAs and at most 50 commits of each repository.
# When none moved, the lock stays as it is and <description> is not written.
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"
use upstream

SUMMARY=50

[ "$#" -ge 1 ] || die "usage: upstream-bump <description> [--lock <file>]"
description=$1
shift
if [ "${1:-}" = --lock ]; then
	[ "$#" -eq 2 ] || die "usage: upstream-bump <description> [--lock <file>]"
	LOCK_FILE=$2
fi
[ -f "${LOCK_FILE}" ] || die "no lock file ${LOCK_FILE}"

work=$(mktemp -d "${TMPDIR:-/tmp}/wrt-bump.XXXXXX")
trap 'rm -rf "${work}"' EXIT INT TERM
names=$(awk '/^[[:space:]]*(#|$)/ { next } { print $1 }' "${LOCK_FILE}")
moved=

for name in ${names}; do
	url=$(lock_field "${name}" url)
	old=$(lock_field "${name}" sha)
	epoch=$(lock_field "${name}" epoch)
	head=$(git ls-remote "${url}" HEAD | cut -f1)
	[ -n "${head}" ] || die "cannot read the head of ${url}"
	[ "${head}" != "${old}" ] || continue
	# The commits since the pinned one: a shallow fetch back to its time.
	git init -q --bare "${work}/${name}"
	git -C "${work}/${name}" fetch -q --shallow-since="$((epoch - 1))" "${url}" "${head}" ||
		die "cannot fetch ${url}"
	new_epoch=$(git -C "${work}/${name}" log -1 --format=%ct "${head}")
	awk -v name="${name}" -v sha="${head}" -v epoch="${new_epoch}" '
		$1 == name && !/^[[:space:]]*#/ { sub($3, sha); sub($4 "$", epoch) }
		{ print }
	' "${LOCK_FILE}" >"${work}/lock"
	cat "${work}/lock" >"${LOCK_FILE}"
	count=$(git -C "${work}/${name}" rev-list --count "${old}..${head}" 2>/dev/null) || count=unknown
	{
		printf '\n### %s: %s commits\n\n```\n' "${name}" "${count}"
		git -C "${work}/${name}" log --oneline --no-decorate "${old}..${head}" 2>/dev/null |
			head -n "${SUMMARY}" || true
		printf '```\n'
	} >"${work}/${name}.log"
	echo "| ${name} | \`${old}\` | \`${head}\` |" >>"${work}/table"
	moved="${moved} ${name}"
done

if [ -z "${moved}" ]; then
	info "upstream has not moved; the lock stays"
	exit 0
fi
today=$(date -u +%Y-%m-%d)
{
	printf 'upstream: bump%s (%s)\n\n' "${moved}" "${today}"
	printf 'The weekly bump of upstream.lock. It merges once its candidate passed\n'
	printf 'the upgrade drill (docs/release-flow.md).\n\n'
	printf '| repository | from | to |\n|---|---|---|\n'
	cat "${work}/table"
	for name in ${moved}; do
		cat "${work}/${name}.log"
	done
} >"${description}"
info "upstream moved:${moved}"
