#!/bin/sh
# build: build the configured tree and collect the outputs with a manifest.
# Usage: scripts/build.sh [profile]   (after fetch, patch and config <profile>)
# Images and the package repository of one run belong together: kmods only load
# on the kernel of the same build (vermagic), so they are collected side by side.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

profile=${1:-dev}

require_linux
require_workdir
ensure_fhs build "$@"

[ -f "${TREE}/.config" ] || die "no .config; run 'just config ${profile}' first"

# ccache_run <args>: the ccache that OpenWrt builds (tools/ccache), on the cache
# directory that rules.mk gives it, $(TOPDIR)/.ccache. OpenWrt prints the cache
# statistics after the build itself, but only into the silenced output.
ccache_run() {
	grep -qx 'CONFIG_CCACHE=y' "${TREE}/.config" || return 0
	ccache="${TREE}/staging_dir/host/bin/ccache"
	[ -x "${ccache}" ] || return 0
	CCACHE_DIR="${TREE}/.ccache" "${ccache}" "$@"
}

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
info "make -j${jobs} (${profile}) on ${cpu}"
status=0
make -C "${TREE}" -j"${jobs}" || status=$?
ccache_run --show-stats --verbose
[ "${status}" -eq 0 ] ||
	die "build failed; rerun 'make -C ${TREE} -j1 V=s' on the failing package for details"

# The kernel configuration overlay must reach the kernel unchanged: a line that
# kconfig dropped (unmet dependency, renamed symbol) would silently lose a feature.
kernel=$(kernel_dir)
missing=$(missing_config_lines "${REPO_DIR}/config/kernel.config" "${kernel}/.config")
if [ -n "${missing}" ]; then
	printf 'error: the kernel configuration lacks these config/kernel.config lines:\n%s\n' "${missing}" >&2
	exit 1
fi
info "kernel configuration overlay applied"

out="${WRT_WORKDIR}/out/${profile}"
rm -rf "${out}"
mkdir -p "${out}/targets" "${out}/packages"
cp -a "${TREE}"/bin/targets/rockchip/armv8/. "${out}/targets/"
cp -a "${TREE}"/bin/packages/. "${out}/packages/"
cp "${WRT_WORKDIR}/out/diffconfig-${profile}" "${out}/diffconfig"

# manifest.json: what was built from what, and the hash of every image and index.
run="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}"
lock_sha256=$(sha256sum "${LOCK_FILE}")
patches_sha256=$(cat "${REPO_DIR}"/patches/*/*.patch | sha256sum)
openwrt_head=$(git -C "${TREE}" rev-parse HEAD)
kernel_version=$(cat "${TREE}"/staging_dir/target-*/kernel.version 2>/dev/null || true)
vermagic=$(cat "${kernel}/.vermagic")
files=$(cd "${out}" && find targets packages -type f \( -name '*.img.gz' -o -name 'packages.adb' \) | sort)
hashes=$(cd "${out}" && printf '%s\n' "${files}" | xargs sha256sum)
printf '%s\n' "${hashes}" | jq -R -n \
	--arg run "${run}" \
	--arg profile "${profile}" \
	--arg lock "${lock_sha256%% *}" \
	--arg patches "${patches_sha256%% *}" \
	--arg head "${openwrt_head}" \
	--arg kernel "${kernel_version}" \
	--arg vermagic "${vermagic}" '
	{
		run: $run,
		profile: $profile,
		upstream_lock_sha256: $lock,
		patches_sha256: $patches,
		openwrt_head: $head,
		kernel_version: $kernel,
		vermagic: $vermagic,
		files: [inputs | capture("^(?<sha>[0-9a-f]+)  (?<path>.+)$") | {(.path): .sha}] | add
	}' >"${out}/manifest.json"
info "outputs in ${out}"
