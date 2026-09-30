#!/bin/sh
# check: run the code-standard checks of design D12; changes nothing.
# Usage: scripts/check.sh [check...]   (all checks when none is named)
# Runs on Linux and macOS with the tools of the quality devShell. NixOS cannot run
# the generic Linux binaries that uv installs (Python, ruff, ty), so there the
# script re-executes inside wrt-test-fhs.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

checks='shfmt shellcheck nixfmt actionlint editorconfig-checker gitleaks forbidden-patterns skeleton marks boards ruff-format ruff-check ty spec-coverage'
requested=$*
for name in ${requested}; do
	case " ${checks} " in
		*" ${name} "*) ;;
		*) die "unknown check '${name}' (checks: ${checks})" ;;
	esac
done

if [ -e /etc/NIXOS ]; then
	ensure_fhs test "$@"
fi

use_tests_venv
cd "${REPO_DIR}"
files=$(repo_files)
shell_files=$(printf '%s\n' "${files}" | xargs shfmt -f)
nix_files=$(printf '%s\n' "${files}" | grep -E '\.nix$')

# forbidden_patterns: build steps must not run or apply downloaded content, nor
# edit upstream files in place (changes to upstream go through patches/).
forbidden_patterns() {
	targets=$(printf '%s\n' "${files}" | grep -E '^(scripts/|\.github/|justfile$)' | grep -v '^scripts/check\.sh$')
	status=0
	# shellcheck disable=SC2086 # targets is a newline-separated list of plain paths
	if grep -nE '(curl|wget)[^|]*\|[[:space:]]*(sudo[[:space:]]+)?(sh|bash|zsh|patch|git[[:space:]]+(am|apply))\b' ${targets}; then
		echo 'remote content piped into a shell or patch tool' >&2
		status=1
	fi
	# shellcheck disable=SC2086
	if grep -nE '(bash|sh)[[:space:]]+<\((curl|wget)' ${targets}; then
		echo 'remote script executed via process substitution' >&2
		status=1
	fi
	# shellcheck disable=SC2086
	if grep -nE '\bsed[[:space:]]+(-[a-zA-Z]*i|--in-place)' ${targets}; then
		echo 'in-place sed edit; change upstream files with patches instead' >&2
		status=1
	fi
	return "${status}"
}

# secrets: no secret in the history, nor in the files about to be committed
# (exactly repo_files, so ignored build and tool directories are never scanned).
secrets() {
	gitleaks git --no-banner --redact --log-level warn || return 1
	snapshot=$(mktemp -d)
	printf '%s\n' "${files}" | tar -cf - -T - | tar -xf - -C "${snapshot}"
	gitleaks dir --no-banner --redact --log-level warn "${snapshot}"
	status=$?
	rm -rf "${snapshot}"
	return "${status}"
}

nl='
'
# shellcheck disable=SC2016 # the literal lines of the skeleton, not expansions
skeleton_body='set -eu
. "$(dirname -- "$0")/lib.sh"'

# complain <message>: report a skeleton violation of ${where}.
complain() {
	printf '%s: %s\n' "${where}" "$*" >&2
	status=1
}

# skeleton: every script follows the skeleton of design D12, and scripts and just
# recipes pair up one to one by name.
skeleton() {
	status=0
	recipes=$(just --summary)
	for where in scripts/*.sh; do
		name=${where#scripts/}
		name=${name%.sh}
		header=$(sed -n '1,3p' "${where}")
		if [ "${name}" = lib ]; then
			[ ! -x "${where}" ] || complain "a sourced library must not be executable"
			case "${header}" in
				"# lib: "*"${nl}# Usage: "*) ;;
				*) complain "header must be '# lib: <purpose>' and '# Usage: ...'" ;;
			esac
			continue
		fi
		[ -x "${where}" ] || complain "not executable"
		case "${header}" in
			"#!/bin/sh${nl}# ${name}: "*".${nl}# Usage: scripts/${name}.sh"*) ;;
			*) complain "header must be '#!/bin/sh', '# ${name}: <purpose>.' and '# Usage: scripts/${name}.sh ...'" ;;
		esac
		body=$(grep -v '^#' "${where}" | sed -n '1,2p')
		[ "${body}" = "${skeleton_body}" ] || complain "the body must start with:${nl}${skeleton_body}"
		case " ${recipes} " in
			*" ${name} "*) ;;
			*) complain "no just recipe named ${name}" ;;
		esac
	done
	where=justfile
	for recipe in ${recipes}; do
		[ "${recipe}" = default ] || [ -f "scripts/${recipe}.sh" ] ||
			complain "recipe ${recipe} has no script scripts/${recipe}.sh"
	done
	return "${status}"
}

failed=
# run <name> <command...>: run a requested check. The command runs in a subshell,
# so the check functions above cannot clobber these variables (POSIX sh has no
# local variables).
run() {
	check=$1
	shift
	case " ${requested:-${check}} " in
		*" ${check} "*) ;;
		*) return 0 ;;
	esac
	if ("$@"); then
		printf 'ok    %s\n' "${check}"
	else
		printf 'FAIL  %s\n' "${check}"
		failed="${failed} ${check}"
	fi
}

# shellcheck disable=SC2086 # file lists are newline-separated plain paths
{
	run shfmt shfmt -d ${shell_files}
	run shellcheck shellcheck ${shell_files}
	run nixfmt nixfmt --check ${nix_files}
	run actionlint actionlint
	run editorconfig-checker editorconfig-checker ${files}
	run gitleaks secrets
	run forbidden-patterns forbidden_patterns
	run skeleton skeleton
	run marks "${REPO_DIR}/scripts/marks-check.sh"
	run boards uv run --directory tests --locked board-check
	run ruff-format uv run --directory tests --locked ruff format --check
	run ruff-check uv run --directory tests --locked ruff check
	run ty uv run --directory tests --locked ty check
	# Structure only: dangling markers, duplicates, the directory rule.
	run spec-coverage uv run --directory tests --locked spec-coverage --summary
}

[ -z "${failed}" ] || die "failed:${failed}"
info "checks passed"
