#!/bin/sh
# Print the pinned host tool versions. The output must be identical on every
# build host (local VM and CI), so it contains no architecture or path.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
ensure_fhs "$@"

first_line() { "$@" 2>&1 | head -n 1; }

printf 'nixpkgs %s\n' "$(jq -r '.nodes.nixpkgs.locked.rev' "$REPO_DIR/flake.lock")"
printf 'bash %s\n' "$(bash -c 'echo "${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}.${BASH_VERSINFO[2]}"')"
printf 'gcc %s\n' "$(gcc -dumpfullversion)"
printf 'g++ %s\n' "$(g++ -dumpfullversion)"
printf 'clang %s\n' "$(clang -dumpversion)"
printf 'llc %s\n' "$(llc --version | sed -n 's/^.*LLVM version \([0-9.]*\).*$/\1/p')"
printf 'make %s\n' "$(first_line make --version)"
printf 'git %s\n' "$(git --version)"
printf 'perl %s\n' "$(perl -e 'print $^V')"
printf 'python3 %s\n' "$(python3 -c 'import platform; print(platform.python_version())')"
printf 'tar %s\n' "$(first_line tar --version)"
printf 'gawk %s\n' "$(first_line awk --version)"
printf 'sed %s\n' "$(first_line sed --version)"
printf 'patch %s\n' "$(first_line patch --version)"
printf 'rsync %s\n' "$(first_line rsync --version)"
printf 'wget %s\n' "$(first_line wget --version)"
printf 'just %s\n' "$(just --version)"
