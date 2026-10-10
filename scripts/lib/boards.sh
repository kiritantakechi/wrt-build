# boards: the supported boards' descriptions (boards/*.json, board-model D1),
# and the table of them the build's A/B hooks read.
# Usage: use boards   (POSIX sh; sourced)
# shellcheck shell=sh
: "${REPO_DIR:?load scripts/lib/core.sh first}"
use tree

BOARDS_DIR="${REPO_DIR}/boards"

# board_ids: the ids of the supported boards (boards/<id>.json), one per line.
board_ids() (
	for description in "${BOARDS_DIR}"/*.json; do
		[ -e "${description}" ] || continue
		name=${description##*/}
		printf '%s\n' "${name%.json}"
	done
)

# board_field <board> <jq filter>: a fact of a board's description. Dies on an
# unknown board, naming the known ones, and on a fact the description lacks.
board_field() (
	description="${BOARDS_DIR}/$1.json"
	if [ ! -f "${description}" ]; then
		known=$(board_ids | tr '\n' ' ')
		die "no board '$1' (boards: ${known% })"
	fi
	jq -er "$2" "${description}" || die "boards/$1.json has no $2"
)

# write_board_table <tree>: each board's U-Boot variant, id and environment
# directory, and its device, for the A/B hooks of uboot-rockchip and of the image
# recipe (env/wrt-boards.mk, board-model D3 and D4).
write_board_table() (
	[ -d "$1" ] || die "write_board_table: no build tree at $1"
	boards=
	devices=
	ids=$(board_ids)
	for board in ${ids}; do
		variant=$(board_field "${board}" .uboot.variant)
		env_dir=$(board_field "${board}" .uboot.env_dir)
		device=$(board_field "${board}" .device)
		boards="${boards:+${boards} }${variant}:${board}:${env_dir}"
		devices="${devices:+${devices} }${device}"
	done
	mkdir -p "$1/env"
	update_file "$1/env/wrt-boards.mk" <<-EOF
		# Written by scripts/lib/boards.sh from boards/*.json (board-model D3, D4): the
		# U-Boot variant, id and environment directory, and the device of every board.
		WRT_AB_BOARDS := ${boards}
		WRT_AB_DEVICES := ${devices}
	EOF
)
