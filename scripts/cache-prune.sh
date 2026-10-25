#!/bin/sh
# cache-prune: delete the caches a run leaves superseded, and on the default branch those of merged branches and closed pull requests.
# Usage: scripts/cache-prune.sh <toolchain key>   (GH_REPO and GITHUB_REF set)
# Of the run's own ref's caches, the current toolchain stays, and so do the
# newest download cache and the newest compiler cache of each stage, the host's
# and each board's. A compiler cache's stage is its key without the settings
# hash and the run, the last two fields, so that a board id with a hyphen is one
# stage (release-integrity D6). A run on the default branch also deletes every
# cache of a branch that no longer exists or that is merged into it, as the
# compare API finds it behind the default branch or identical (build-integrity
# D6), and of a pull request that is closed. Caches go by id or by ref, never by
# key alone, which other refs' caches may share. A cache GitHub evicted
# meanwhile is gone either way.
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"

toolchain=${1:-}

[ -n "${toolchain}" ] || die "usage: cache-prune <toolchain key>"
[ -n "${GH_REPO:-}" ] && [ -n "${GITHUB_REF:-}" ] || die "GH_REPO and GITHUB_REF must be set"

# The ids of the superseded caches of the run's ref, newest first.
superseded=$(
	gh cache list --ref "${GITHUB_REF}" --limit 100 --sort created_at --order desc \
		--json id,key --jq '.[] | "\(.id) \(.key)"' |
		awk -v toolchain="${toolchain}" '
			$2 ~ /^toolchain-/ { if ($2 != toolchain) print $1; next }
			$2 ~ /^dl-/ { if (kept["dl"]++) print $1; next }
			$2 ~ /^compiler-cache-/ { stage = $2; sub(/-[^-]*-[^-]*$/, "", stage); if (kept[stage]++) print $1 }
		'
)
for id in ${superseded}; do
	info "deleting superseded cache ${id}"
	gh cache delete "${id}" || info "cache ${id} was not deleted"
done

default=$(gh api "repos/${GH_REPO}" --jq .default_branch)
[ "${GITHUB_REF}" = "refs/heads/${default}" ] || exit 0
branches=$(gh api --paginate "repos/${GH_REPO}/branches" --jq '.[].name')
refs=$(gh cache list --limit 1000 --json ref --jq '[.[].ref] | unique | .[]')
for ref in ${refs}; do
	case "${ref}" in
		"refs/heads/${default}") continue ;;
		refs/heads/*)
			name=${ref#refs/heads/}
			if printf '%s\n' "${branches}" | grep -Fqx -- "${name}"; then
				status=$(gh api "repos/${GH_REPO}/compare/${default}...${name}" --jq .status)
				case "${status}" in
					behind | identical) why="merged into ${default}" ;;
					*) continue ;;
				esac
			else
				why="deleted"
			fi
			;;
		refs/pull/*/merge)
			name=${ref#refs/pull/}
			name=${name%/merge}
			state=$(gh api "repos/${GH_REPO}/pulls/${name}" --jq .state)
			[ "${state}" = closed ] || continue
			name="pull request ${name}"
			why="closed"
			;;
		*) continue ;;
	esac
	info "deleting the caches of ${name}, ${why}"
	gh cache delete --all --ref "${ref}" || info "the caches of ${name} were not all deleted"
done
