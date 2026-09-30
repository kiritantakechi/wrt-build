#!/bin/sh
# boards: print boards' ids as a JSON list (board-model D1).
# Usage: scripts/boards.sh [board...]
# Without a board, every supported board: one id per description under boards/,
# sorted; CI builds, tests and releases each of them. With boards, those boards,
# each checked to be supported first: a build checks its board this way before
# anything else runs, and fails naming the supported ones.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

for board in "$@"; do
	board_field "${board}" .device >/dev/null
done
ids=$(board_ids)
[ "$#" -eq 0 ] || ids=$(printf '%s\n' "$@")
printf '%s\n' "${ids}" | jq -Rsc 'split("\n") | map(select(. != ""))'
