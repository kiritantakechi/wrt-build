#!/bin/sh
# github-audit: check the GitHub settings the release pipeline relies on (r4s-release-pipeline D7).
# Usage: scripts/github-audit.sh [owner/repository]
# Settings, not code, so they are read back from GitHub (gh api):
#  - the release-signing environment waits for a reviewer's approval before any
#    job that uses it runs, and only main and bump/* may deploy to it;
#  - main's rules require the checks check and upgrade-drill, so no bump is
#    merged unless its candidate passed the drill.
# Reports every finding, then fails if there was one.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

repository=${1:-${GITHUB_REPOSITORY:-kiritantakechi/wrt-build}}
ENVIRONMENT=release-signing
# The branches that may deploy to it, as gh lists them: sorted, one line.
BRANCHES="bump/* main"
CHECKS="check upgrade-drill"
status=0

fail() {
	printf 'FAIL  %s\n' "$*"
	status=1
}

pass() {
	printf 'ok    %s\n' "$*"
}

environment=$(gh api "repos/${repository}/environments/${ENVIRONMENT}" 2>/dev/null) || environment=
if [ -z "${environment}" ]; then
	fail "no environment ${ENVIRONMENT}"
else
	reviewers=$(printf '%s' "${environment}" |
		jq '[.protection_rules[]? | select(.type == "required_reviewers") | .reviewers[]?] | length')
	if [ "${reviewers}" -gt 0 ]; then
		pass "${ENVIRONMENT} waits for one of ${reviewers} reviewer(s)"
	else
		fail "${ENVIRONMENT} runs without a reviewer's approval"
	fi
	policies=$(gh api "repos/${repository}/environments/${ENVIRONMENT}/deployment-branch-policies" \
		--jq '[.branch_policies[].name] | sort | join(" ")' 2>/dev/null) || policies=
	if [ "${policies}" = "${BRANCHES}" ]; then
		pass "${ENVIRONMENT} deploys from ${BRANCHES} only"
	else
		fail "${ENVIRONMENT} deploys from '${policies}', not from ${BRANCHES} only"
	fi
fi

required=$(gh api "repos/${repository}/rules/branches/main" \
	--jq '[.[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context] | join(" ")' \
	2>/dev/null) || required=
for check in ${CHECKS}; do
	case " ${required} " in
		*" ${check} "*) pass "main requires ${check}" ;;
		*) fail "main does not require ${check}" ;;
	esac
done

[ "${status}" -eq 0 ] || die "the repository's settings do not hold what the release pipeline needs"
info "the repository's settings hold"
