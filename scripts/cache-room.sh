#!/bin/sh
# cache-room: say whether a cache of the paths fits next to the repository's caches, as save=true|false.
# Usage: scripts/cache-room.sh <path>... >>"$GITHUB_OUTPUT"   (GH_REPO and GITHUB_REF set)
# GitHub keeps CACHE_QUOTA of caches per repository and evicts the least recently
# used past it, of any ref. Every run restores the default branch's caches, so a
# run on another ref must not push them out (build-integrity D5): it saves a
# cache only while the caches present, its own older ones included, and the
# paths stay within the quota. The paths count at their size on disk, which a
# save compresses, so that the estimate errs on the side of main's caches. A run
# on the default branch always saves, and prunes what it superseded afterwards
# (cache-prune.sh). The toolchain is saved without asking: the firmware jobs
# restore it or fail.
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"

# 10 GB, the repository's limit, read as the smaller of its two meanings.
CACHE_QUOTA=${CACHE_QUOTA:-10000000000}

[ "$#" -gt 0 ] || die "usage: cache-room <path>..."
[ -n "${GH_REPO:-}" ] && [ -n "${GITHUB_REF:-}" ] || die "GH_REPO and GITHUB_REF must be set"

default=$(gh api "repos/${GH_REPO}" --jq .default_branch)
if [ "${GITHUB_REF}" = "refs/heads/${default}" ]; then
	info "${GITHUB_REF} is the default branch: saving"
	echo save=true
	exit 0
fi
used=$(gh api "repos/${GH_REPO}/actions/cache/usage" --jq .active_caches_size_in_bytes)
size=$(du -sk -- "$@" | awk '{ size += $1 } END { print size * 1024 }')
if [ $((used + size)) -le "${CACHE_QUOTA}" ]; then
	info "${size} bytes fit next to the ${used} bytes of caches present: saving"
	echo save=true
else
	info "${size} bytes do not fit next to the ${used} bytes of caches present (quota ${CACHE_QUOTA}): not saving"
	echo save=false
fi
