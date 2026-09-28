#!/bin/sh
# Repository checks that run on any host (including macOS).
#  - no build step may download a script or patch and execute or apply it;
#  - no build step may edit the upstream tree in place with sed -i;
#  - every shell script passes shellcheck.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

cd "$REPO_DIR"
status=0

targets=$(find scripts .github -type f \( -name '*.sh' -o -name '*.yml' -o -name '*.yaml' \) 2>/dev/null |
	grep -v '^scripts/lint\.sh$' || true)
[ -f justfile ] && targets="$targets justfile"

check() {
	pattern=$1 reason=$2
	# shellcheck disable=SC2086 # targets is a whitespace-separated file list
	if hits=$(grep -nE -- "$pattern" $targets 2>/dev/null); then
		printf 'lint: %s\n%s\n' "$reason" "$hits" >&2
		status=1
	fi
}

check '(curl|wget)[^|]*\|[[:space:]]*(sudo[[:space:]]+)?(sh|bash|zsh|patch|git[[:space:]]+(am|apply))\b' \
	'remote content piped into a shell or patch tool'
check '(bash|sh)[[:space:]]+<\((curl|wget)' 'remote script executed via process substitution'
check '\bsed[[:space:]]+(-[a-zA-Z]*i|--in-place)' 'in-place sed edit; change upstream files with patches instead'

if command -v shellcheck >/dev/null 2>&1; then
	# shellcheck disable=SC2046 # word splitting of the file list is intended
	shellcheck -x -s sh $(find scripts .github -type f -name '*.sh') || status=1
else
	info "shellcheck not found; skipping (it is provided by 'nix develop')"
fi

if [ "$status" -eq 0 ]; then
	info "lint ok"
fi
exit "$status"
