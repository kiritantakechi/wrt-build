#!/bin/sh
# cache-room: say whether a cache of the paths fits next to the repository's caches, as save=true|false.
# Usage: scripts/cache-room.sh <path>... >>"$GITHUB_OUTPUT"   (GH_REPO and GITHUB_REF set; CACHE_SAVERS)
# GitHub keeps CACHE_QUOTA of caches per repository and evicts the least recently
# used past it, of any ref. Every run restores the default branch's caches, so a
# run on another ref must not push them out (build-integrity D5): it saves a
# cache only while the caches present, its own older ones included, and the
# paths stay within the quota. The paths count at their size on disk, which a
# save compresses, so that the estimate errs on the side of main's caches, and
# CACHE_SAVERS times over: the jobs of a matrix each ask while none has saved
# yet, so each counts the room for all of them (release-integrity D6). A run
# on the default branch always saves, and prunes what it superseded afterwards
# (cache-prune.sh). The toolchain is saved without asking: the firmware jobs
# restore it or fail.
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"

# 10 GB, the repository's limit, read as the smaller of its two meanings.
CACHE_QUOTA=${CACHE_QUOTA:-10000000000}
# The jobs that may save a cache like this one at the same time.
CACHE_SAVERS=${CACHE_SAVERS:-1}

[ "$#" -gt 0 ] || die "usage: cache-room <path>..."
case "${CACHE_SAVERS}" in
	'' | 0* | *[!0-9]*) die "CACHE_SAVERS must be a positive number: ${CACHE_SAVERS}" ;;
	*) ;;
esac
[ -n "${GH_REPO:-}" ] && [ -n "${GITHUB_REF:-}" ] || die "GH_REPO and GITHUB_REF must be set"

default=$(gh api "repos/${GH_REPO}" --jq .default_branch)
if [ "${GITHUB_REF}" = "refs/heads/${default}" ]; then
	info "${GITHUB_REF} is the default branch: saving"
	echo save=true
	exit 0
fi
used=$(gh api "repos/${GH_REPO}/actions/cache/usage" --jq .active_caches_size_in_bytes)
size=$(du -sk -- "$@" | awk -v savers="${CACHE_SAVERS}" '{ size += $1 } END { print size * 1024 * savers }')
if [ $((used + size)) -le "${CACHE_QUOTA}" ]; then
	info "${size} bytes for ${CACHE_SAVERS} saving jobs fit next to the ${used} bytes of caches present: saving"
	echo save=true
else
	info "${size} bytes for ${CACHE_SAVERS} saving jobs do not fit next to the ${used} bytes of caches present (quota ${CACHE_QUOTA}): not saving"
	echo save=false
fi
