# seeds: the configuration of a build composed from seeds: a profile's
# (config/profiles), and a board's (board-model D2).
# Usage: use seeds   (POSIX sh; sourced)
# shellcheck shell=sh
: "${REPO_DIR:?load scripts/lib/core.sh first}"
use boards

# profile_seeds <profile>: the seeds of a profile (config/profiles), in order. Those
# after a "|" apply to a board's configuration only, never to the board-neutral one
# the toolchain is built from (toolchain-o3 D5).
profile_seeds() (
	awk -v p="$1" -F: '
		/^[[:space:]]*(#|$)/ { next }
		$1 == p { print $2; found = 1 }
		END { if (!found) exit 1 }
	' "${REPO_DIR}/config/profiles" || die "unknown profile '$1' (see config/profiles)"
)

# build_name <board> <profile>: the name of a board's build directories and
# binaries (CONFIG_BUILD_SUFFIX): the board's, and after it the profile's for a
# profile with board-only seeds, whose objects differ from every other profile's.
build_name() (
	seeds=$(profile_seeds "$2") || exit
	case "${seeds}" in
		*"|"*) echo "$1_$2" ;;
		*) echo "$1" ;;
	esac
)

# merge_seeds <file>...: the lines of the seed files in order, each option only in
# the last line that sets it (CONFIG_X=..., or "# CONFIG_X is not set"), where
# that line stands: a later seed's line replaces an earlier one, and the
# composition holds one line per option. Comments and blank lines stay.
merge_seeds() (
	awk -f "${REPO_DIR}/scripts/lib/merge-seeds.awk" "$@"
)

# compose_seeds <tree> <profile> <board> <output>: the profile's seed files in
# order (config/profiles), merged one line per option, then the board's seed
# (board-model D2): its device, its -mcpu after the profile's optimization flags,
# and build and output directories of its own in <tree> (build_name). Without a
# board (an empty <board>), the configuration is the board-neutral one the host
# tools and the toolchain are built from: the seeds before any "|", every board's
# device, none of their CPU tuning, and no other device, which buildbot mode
# would otherwise add.
compose_seeds() (
	[ -d "$1" ] || die "compose_seeds: no build tree at $1"
	tree=$1 profile=$2 board=$3 output=$4
	seeds=$(profile_seeds "${profile}") || exit
	if [ -z "${board}" ]; then
		seeds=${seeds%%|*}
	else
		seeds=$(printf '%s\n' "${seeds}" | tr '|' ' ')
	fi
	set --
	for seed in ${seeds}; do
		file="${REPO_DIR}/config/${seed}.seed"
		[ -f "${file}" ] || die "missing seed file config/${seed}.seed"
		set -- "$@" "${file}"
	done
	merged=$(merge_seeds "$@")
	if [ -z "${board}" ]; then
		ids=$(board_ids)
		{
			printf '%s\n' "${merged}"
			cat <<-EOF
				# Every board, with none of their CPU tuning (board-model D2).
				CONFIG_TARGET_MULTI_PROFILE=y
				# CONFIG_TARGET_ALL_PROFILES is not set
				# CONFIG_TARGET_PER_DEVICE_ROOTFS is not set
			EOF
			for id in ${ids}; do
				device=$(board_field "${id}" .device)
				echo "CONFIG_TARGET_DEVICE_rockchip_armv8_DEVICE_${device}=y"
			done
		} >"${output}"
		return 0
	fi
	device=$(board_field "${board}" .device)
	cpu=$(board_field "${board}" .cpu)
	name=$(build_name "${board}" "${profile}") || exit
	extra=$(printf '%s\n' "${merged}" | sed -n 's/^CONFIG_EXTRA_OPTIMIZATION="\(.*\)"$/\1/p')
	{
		printf '%s\n' "${merged}" | grep -v '^CONFIG_EXTRA_OPTIMIZATION='
		cat <<-EOF
			# The board: boards/${board}.json (board-model D2).
			CONFIG_TARGET_rockchip_armv8_DEVICE_${device}=y
			CONFIG_EXTRA_OPTIMIZATION="${extra:+${extra} }-mcpu=${cpu}"
			CONFIG_BUILD_SUFFIX="${name}"
			CONFIG_BINARY_FOLDER="${tree}/bin/${name}"
		EOF
	} >"${output}"
)
