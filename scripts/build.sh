#!/bin/sh
# build: build a board's configured tree and collect the outputs with a manifest.
# Usage: scripts/build.sh <board> [profile]   (after fetch, patch, toolchain-build and config)
# With WRT_COMPILER_CACHE_TRIM set, every compiler cache keeps only what the build
# used.
# It ends with the stages that took the most time, from OpenWrt's build time log
# (build-acceleration D1), which stays in the tree's logs/.
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
name=$(build_name "${board}" "${profile}")
grep -qx "CONFIG_BUILD_SUFFIX=\"${name}\"" "${TREE}/.config" ||
	die "the tree is not configured for ${board} (${profile}); run 'just config ${board} ${profile}' first"

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
rust_std=$(toolchain_rust_std)
recorded=$(jq -r '.rust_std // ""' "${record}")
[ "${rust_std}" = "${recorded}" ] ||
	die "Rust's standard library is not the one the toolchain's record names; run 'just toolchain-build'"

jobs=${WRT_JOBS:-$(nproc)}
# Build times depend on the CPU, which differs between CI runners. lscpu names some
# cores (Apple's) only by their vendor.
cpu=$(lscpu | awk -F ': *' '
	$1 == "Vendor ID" { vendor = $2 }
	$1 == "Model name" && $2 != "-" { model = $2 }
	END { print (model != "" ? model : vendor) }')
info "make download"
make -C "${TREE}" -j"${jobs}" download
# Statistics of this build alone: the caches carry them from earlier builds.
start=$(compiler_cache_start)
# The UB-indicative warnings of each package's last build (toolchain-o3 D4), kept
# with the board's build directories, which live as long as what they record.
build_dir=$(make -C "${TREE}" -s val.BUILD_DIR)
warnings="${build_dir}/wrt-warnings"
mkdir -p "${warnings}"
touch "${warnings}/.since"
info "make -j${jobs} (${board}, ${profile}) on ${cpu}"
# The time log is named after the build directories, as each build keeps its own.
log=$(time_log "${name}")
status=0
BUILD_TIME_LOG="${log}" make -C "${TREE}" -j"${jobs}" || status=$?
# Also after a failure: the next build may rewrite these logs without a compile.
warnings_harvest "${TREE}/logs" "${warnings}" "${warnings}/.since"
compiler_cache_report "${start}"
time_report "${log}"
[ "${status}" -eq 0 ] ||
	die "build failed; rerun 'make -C ${TREE} -j1 V=s' on the failing package for details"
# WRT_COMPILER_CACHE_TRIM (CI, where each board's cache is its own): drop what this
# build did not use. Entries of an earlier toolchain or kernel configuration would
# otherwise pile up past the cache quota. Locally the boards share the caches,
# which keep everything up to their own limits.
if [ -n "${WRT_COMPILER_CACHE_TRIM:-}" ]; then
	compiler_cache_trim "${start}"
fi
# The board's build left the shared toolchain alone (build-acceleration D7).
libc_after=$(toolchain_libc "${toolchain_dir}")
[ "${libc_after}" = "${libc}" ] ||
	die "the build rebuilt the toolchain's C library with ${board}'s flags; run 'just toolchain-build' and build again"
rust_std_after=$(toolchain_rust_std)
[ "${rust_std_after}" = "${rust_std}" ] ||
	die "the build rebuilt Rust's standard library with ${board}'s flags; run 'just toolchain-build' and build again"
compiled=$(toolchain_stages "${log}" | paste -sd ',' -)
[ -z "${compiled}" ] ||
	die "the build compiled part of the toolchain, which only 'just toolchain-build' builds: ${compiled}"

# A sanitizer in trap mode needs no runtime, and OpenWrt's musl toolchain has
# none: no file of the root filesystem may call into one (toolchain-o3 D5).
if grep -q '^CONFIG_TARGET_OPTIMIZATION=".*-fsanitize-trap=' "${TREE}/.config"; then
	nm="${toolchain_dir}/bin/$(make -C "${TREE}" -s val.TARGET_CROSS)nm"
	root=$(make -C "${TREE}" -s val.TARGET_DIR)
	calls=$(find "${root}" -type f -exec sh -c '
		nm=$1
		shift
		for file; do
			"${nm}" -D --undefined-only "${file}" 2>/dev/null | grep -q " __ubsan_" &&
				printf "%s\n" "${file}"
		done
		exit 0' sh "${nm}" {} +)
	if [ -n "${calls}" ]; then
		printf 'error: these files call into a UBSan runtime the toolchain lacks:\n%s\n' "${calls}" >&2
		exit 1
	fi
	info "no file calls into a UBSan runtime"
fi

# The kernel configuration overlay must reach the kernel unchanged: a line that
# kconfig dropped (unmet dependency, renamed symbol) would silently lose a feature.
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

# warnings.json: the UB-indicative warnings of the packages in the board's image,
# for the system tests' register check (quality/undefined-behavior).
found=$(image_warnings "${bin_dir}/"*"-${device}.manifest" "${TREE}/tmp/.packageinfo" "${warnings}")
printf '%s' "${found}" | jq -R -n '[inputs | split("\t")
		| {package: .[0], option: .[1], file: .[2], function: .[3], line: (.[4] | tonumber)}]' \
	>"${out}/warnings.json"
count=$(jq 'length' "${out}/warnings.json")
info "${count} UB-indicative warnings in the image's packages"

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
# The flags the kernel build adds (KCFLAGS of include/kernel.mk), as the target's
# makefile evaluates them, without the maps of the build's paths.
target=$(make -C "${TREE}" -s val.BOARD)
kernel_cflags=$(make -C "${TREE}/target/linux/${target}" -s TOPDIR="${TREE}" val.KERNEL_MAKE_FLAGS |
	sed -n 's/^KCFLAGS="\([^"]*\)".*/\1/p' | tr ' ' '\n' | grep -v -e '-prefix-map=' -e '^$' | paste -sd ' ' -)
[ -n "${kernel_cflags}" ] || die "found no kernel flags in target/linux/${target}'s KERNEL_MAKE_FLAGS"
files=$(cd "${out}" && find . -type f \( -name '*.gz' -o -name 'packages.adb' -o -name 'u-boot*' -o -name 'kernel.config' \) | sed 's|^\./||' | sort)
hashes=$(cd "${out}" && printf '%s\n' "${files}" | xargs sha256sum)
printf '%s\n' "${hashes}" | jq -R -n \
	--arg board "${board}" \
	--arg device "${device}" \
	--arg run "${run}" \
	--arg profile "${profile}" \
	--arg cflags "${cflags}" \
	--arg kernel_cflags "${kernel_cflags}" \
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
		kernel_cflags: $kernel_cflags,
		toolchain_cflags: $toolchain_cflags,
		upstream_lock_sha256: $lock,
		patches_sha256: $patches,
		openwrt_head: $head,
		kernel_version: $kernel,
		vermagic: $vermagic,
		files: [inputs | capture("^(?<sha>[0-9a-f]+)  (?<path>.+)$") | {(.path): .sha}] | add
	}' >"${out}/manifest.json"
info "outputs in ${out}"
