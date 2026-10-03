#!/bin/sh
# toolchain-build: build the host tools and the board-neutral toolchain of every language.
# Usage: scripts/toolchain-build.sh [profile]   (default dev)
# The toolchain is the cross toolchain and the Go and Rust host toolchains built
# on it (build-acceleration D2). The script ends with the stages that took the
# most time (build-acceleration D1).
# Every board builds on this one toolchain (board-model D2), so it is built from
# the profile's configuration without a board: its C library and Rust's standard
# library carry no board's -mcpu. The flags it was built with and the hashes of
# both libraries go to wrt-toolchain.json in the toolchain directory, which
# build.sh checks. The record is written as soon as the cross toolchain is
# built, and again with Rust's library, so a failed Go or Rust build leaves the
# cross toolchain to the next run. The toolchain stays only while the
# configuration's flags are the recorded ones and both libraries are the ones
# the record names: one without a record predates the board model, one with
# another library was rebuilt by a board's build with that board's flags, and
# one of other flags would build packages that keep objects of the old ones, so
# each is built anew.
# The tree is left configured without a board; config configures it for one.
# make world skips toolchain/compile only while the toolchain's compile stamp is up
# to date, and toolchain/install does not write it. The packed archive has no
# build_dir/toolchain-*, so without the stamp world would rebuild the whole cross
# toolchain on top of the cached one; the stamp is built here as well. So is its
# version stamp: in buildbot mode (the ci profile) every make in the tree deletes
# the toolchain, with the board's build and staging directories, unless the
# stamp names the last commit of toolchain/ (toolchain/Makefile), and a toolchain
# built without buildbot mode has none.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

profile=${1:-dev}

require_linux
require_workdir
ensure_fhs build "$@"

[ -f "${TREE}/feeds.conf" ] || die "no source tree; run 'just fetch' and 'just patch' first"
link_tree
write_board_table
wanted="${WRT_WORKDIR}/out/seed-toolchain-${profile}.config"
compose_seeds "${profile}" "" "${wanted}"
info "make defconfig (toolchain, ${profile})"
configure_tree "${wanted}"

toolchain_dir=$(make -C "${TREE}" -s val.TOOLCHAIN_DIR)
record="${toolchain_dir}/wrt-toolchain.json"
cflags=$(make -C "${TREE}" -s val.TARGET_CFLAGS)
# Rust's standard library has C parts compiled with the target's flags, so it
# goes with the C toolchain whenever that is built anew.
if [ -d "${toolchain_dir}" ]; then
	recorded=$(jq -r '[.cflags, .libc] | map(. // "") | join(" | ")' "${record}" 2>/dev/null) || recorded=
	libc=$(toolchain_libc "${toolchain_dir}")
	if [ "${recorded}" != "${cflags} | ${libc}" ] || [ -z "${libc}" ]; then
		info "the toolchain in ${toolchain_dir} is not the one its record names: building it anew"
		rm -rf "${toolchain_dir}" "${TREE}"/build_dir/toolchain-*
		make -C "${TREE}" package/feeds/packages/rust/host/clean >/dev/null
	fi
fi
recorded=$(jq -r '.rust_std // ""' "${record}" 2>/dev/null) || recorded=
rust_std=$(toolchain_rust_std)
if [ -n "${rust_std}" ] && [ "${rust_std}" != "${recorded}" ]; then
	info "Rust's standard library is not the one the record names: building it anew"
	make -C "${TREE}" package/feeds/packages/rust/host/clean >/dev/null
fi
# write_record <rust_std>: what this configuration built, or found built as
# recorded; Rust's library only once there is one.
write_record() {
	jq -n --arg cflags "${cflags}" --arg libc "${libc}" --arg rust_std "$1" \
		'{cflags: $cflags, libc: $libc} + if $rust_std == "" then {} else {rust_std: $rust_std} end' \
		>"${record}"
}

jobs=${WRT_JOBS:-$(nproc)}
log=$(time_log host)
start=$(compiler_cache_start)
status=0
BUILD_TIME_LOG="${log}" make -C "${TREE}" -j"${jobs}" tools/install toolchain/install || status=$?
if [ "${status}" -eq 0 ]; then
	[ -d "${toolchain_dir}" ] || die "no toolchain directory at '${toolchain_dir}'"
	# toolchain/Makefile: $(call stampfile,toolchain,compile) in $(TOOLCHAIN_DIR),
	# and the version stamp as its buildbot mode writes it.
	make -C "${TREE}" "${toolchain_dir}/stamp/.toolchain_compile"
	version=$(git -C "${TREE}" log --no-show-signature --format=%h -1 toolchain)
	printf '%s\n' "${version}" | update_file "${toolchain_dir}/stamp/.ver_check"
	libc=$(toolchain_libc "${toolchain_dir}")
	[ -n "${libc}" ] || die "the toolchain in ${toolchain_dir} has no C library"
	# Rust's library is the recorded one here, or none: the checks above removed
	# any other.
	rust_std=$(toolchain_rust_std)
	write_record "${rust_std}"
	# The host toolchains of the other languages the firmware is written in, on the
	# cross toolchain (build-acceleration D2): no board's build compiles them again.
	BUILD_TIME_LOG="${log}" make -C "${TREE}" -j"${jobs}" \
		package/feeds/packages/golang/host/compile package/feeds/packages/rust/host/compile || status=$?
fi
compiler_cache_report "${start}"
time_report "${log}"
[ "${status}" -eq 0 ] || die "building the host tools and the toolchains failed"
# WRT_COMPILER_CACHE_TRIM (CI, where the host stage keeps a cache of its own): drop
# what this build did not use.
if [ -n "${WRT_COMPILER_CACHE_TRIM:-}" ]; then
	compiler_cache_trim "${start}"
fi
rust_std=$(toolchain_rust_std)
[ -n "${rust_std}" ] || die "no Rust standard library in staging_dir/hostpkg"
write_record "${rust_std}"
info "toolchains built with: ${cflags}"
info "toolchains ready in ${toolchain_dir} and staging_dir/hostpkg"
