#!/bin/sh
# build: build a board's configured tree and collect the outputs with a manifest.
# Usage: scripts/build.sh <board> [profile]   (after fetch, patch, toolchain-build and config)
# Images and the package repository of one run belong together: kmods only load
# on the kernel of the same build (vermagic), so they are collected side by side,
# in $WRT_WORKDIR/out/<board>/<profile>. The toolchain must be the board-neutral
# one (board-model D2): recorded by toolchain-build, with no board's -mcpu, and
# left alone by the build.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

board=${1:-}
profile=${2:-dev}

require_linux
require_workdir
ensure_fhs build "$@"

[ -n "${board}" ] || die "usage: build <board> [profile]"
device=$(board_field "${board}" .device)
[ -f "${TREE}/.config" ] || die "no .config; run 'just config ${board} ${profile}' first"
grep -qx "CONFIG_BUILD_SUFFIX=\"${board}\"" "${TREE}/.config" ||
	die "the tree is not configured for ${board}; run 'just config ${board} ${profile}' first"

# ccache_run <args>: the ccache that OpenWrt builds (tools/ccache), on the cache
# directory that rules.mk gives it, $(TOPDIR)/.ccache. OpenWrt prints the cache
# statistics after the build itself, but only into the silenced output.
ccache_run() {
	grep -qx 'CONFIG_CCACHE=y' "${TREE}/.config" || return 0
	ccache="${TREE}/staging_dir/host/bin/ccache"
	[ -x "${ccache}" ] || return 0
	CCACHE_DIR="${TREE}/.ccache" "${ccache}" "$@"
}

toolchain_dir=$(make -C "${TREE}" -s val.TOOLCHAIN_DIR)
record="${toolchain_dir}/wrt-toolchain.json"
[ -f "${record}" ] || die "the toolchain has no record of its flags; run 'just toolchain-build'"
toolchain_cflags=$(jq -r .cflags "${record}")
ids=$(board_ids)
for other in ${ids}; do
	mcpu="-mcpu=$(board_field "${other}" .cpu)"
	case " ${toolchain_cflags} " in
		*" ${mcpu} "*) die "the toolchain was built with ${other}'s ${mcpu}; run 'just toolchain-build'" ;;
		*) ;;
	esac
done
libc=$(toolchain_libc "${toolchain_dir}")
recorded=$(jq -r .libc "${record}")
[ "${libc}" = "${recorded}" ] ||
	die "the toolchain's C library is not the one its record names; run 'just toolchain-build'"

jobs=${WRT_JOBS:-$(nproc)}
# Build times depend on the CPU, which differs between CI runners. lscpu names some
# cores (Apple's) only by their vendor.
cpu=$(lscpu | awk -F ': *' '
	$1 == "Vendor ID" { vendor = $2 }
	$1 == "Model name" && $2 != "-" { model = $2 }
	END { print (model != "" ? model : vendor) }')
info "make download"
make -C "${TREE}" -j"${jobs}" download
# Statistics of this build alone: the cache itself carries them from earlier builds.
ccache_run --zero-stats >/dev/null
info "make -j${jobs} (${board}, ${profile}) on ${cpu}"
status=0
make -C "${TREE}" -j"${jobs}" || status=$?
ccache_run --show-stats --verbose
[ "${status}" -eq 0 ] ||
	die "build failed; rerun 'make -C ${TREE} -j1 V=s' on the failing package for details"
libc_after=$(toolchain_libc "${toolchain_dir}")
[ "${libc_after}" = "${libc}" ] ||
	die "the build rebuilt the toolchain's C library with ${board}'s flags; run 'just toolchain-build' and build again"

# The kernel configuration overlay must reach the kernel unchanged: a line that
# kconfig dropped (unmet dependency, renamed symbol) would silently lose a feature.
build_dir=$(make -C "${TREE}" -s val.BUILD_DIR)
kernel=$(kernel_dir "${build_dir}")
missing=$(missing_config_lines "${REPO_DIR}/config/kernel.config" "${kernel}/.config")
if [ -n "${missing}" ]; then
	printf 'error: the kernel configuration lacks these config/kernel.config lines:\n%s\n' "${missing}" >&2
	exit 1
fi
info "kernel configuration overlay applied"

# The board's own output directory (BINARY_FOLDER) and build and staging
# directories (BUILD_SUFFIX).
bin_dir=$(make -C "${TREE}" -s val.BIN_DIR)
output_dir=$(make -C "${TREE}" -s val.OUTPUT_DIR)
staging_dir=$(make -C "${TREE}" -s val.STAGING_DIR)
out="${WRT_WORKDIR}/out/${board}/${profile}"
rm -rf "${out}"
mkdir -p "${out}/targets" "${out}/packages"
cp -a "${bin_dir}/." "${out}/targets/"
cp -a "${output_dir}/packages/." "${out}/packages/"
cp "${WRT_WORKDIR}/out/${board}/diffconfig-${profile}" "${out}/diffconfig"

# The configuration of what only the board's SoC runs, for the tests that check it
# statically, and the emulator's U-Boot (r4s-ab-rollback design D7).
uboot_build() {
	set -- "${build_dir}/u-boot-$1"/u-boot-*
	[ "$#" -eq 1 ] && [ -d "$1" ] || die "expected one build of u-boot-$1, found: $*"
	printf '%s\n' "$1"
}
variant=$(board_field "${board}" .uboot.variant)
board_uboot=$(uboot_build "${variant}")
qemu_uboot=$(uboot_build wrt-qemu)
cp "${kernel}/.config" "${out}/kernel.config"
cp "${board_uboot}/.config" "${out}/u-boot.config"
cp "${qemu_uboot}/.config" "${out}/u-boot-qemu.config"
cp "${staging_dir}/image/wrt-qemu-u-boot.bin" "${out}/u-boot-qemu.bin"

# manifest.json: which board (and its OpenWrt device) was built from what and
# with which flags, and the hash of every image, index, configuration and
# firmware above.
run="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}"
lock_sha256=$(sha256sum "${LOCK_FILE}")
patches_sha256=$(cat "${REPO_DIR}"/patches/*/*.patch | sha256sum)
openwrt_head=$(git -C "${TREE}" rev-parse HEAD)
kernel_version=$(cat "${staging_dir}/kernel.version" 2>/dev/null || true)
vermagic=$(cat "${kernel}/.vermagic")
cflags=$(make -C "${TREE}" -s val.TARGET_CFLAGS)
files=$(cd "${out}" && find . -type f \( -name '*.gz' -o -name 'packages.adb' -o -name 'u-boot*' -o -name 'kernel.config' \) | sed 's|^\./||' | sort)
hashes=$(cd "${out}" && printf '%s\n' "${files}" | xargs sha256sum)
printf '%s\n' "${hashes}" | jq -R -n \
	--arg board "${board}" \
	--arg device "${device}" \
	--arg run "${run}" \
	--arg profile "${profile}" \
	--arg cflags "${cflags}" \
	--arg toolchain_cflags "${toolchain_cflags}" \
	--arg lock "${lock_sha256%% *}" \
	--arg patches "${patches_sha256%% *}" \
	--arg head "${openwrt_head}" \
	--arg kernel "${kernel_version}" \
	--arg vermagic "${vermagic}" '
	{
		board: $board,
		device: $device,
		run: $run,
		profile: $profile,
		cflags: $cflags,
		toolchain_cflags: $toolchain_cflags,
		upstream_lock_sha256: $lock,
		patches_sha256: $patches,
		openwrt_head: $head,
		kernel_version: $kernel,
		vermagic: $vermagic,
		files: [inputs | capture("^(?<sha>[0-9a-f]+)  (?<path>.+)$") | {(.path): .sha}] | add
	}' >"${out}/manifest.json"
info "outputs in ${out}"
