#!/bin/sh
# toolchain-build: build the host tools and the board-neutral cross toolchain.
# Usage: scripts/toolchain-build.sh [profile]   (default dev)
# It ends with the stages that took the most time (build-acceleration D1).
# Every board builds on this one toolchain (board-model D2), so it is built from
# the profile's configuration without a board: its C library carries no board's
# -mcpu. The flags it was built with and the hash of its C library go to
# wrt-toolchain.json in the toolchain directory, which build.sh checks. A
# toolchain stays only while its C library is the one the record names: one
# without a record predates the board model, and one with another C library was
# rebuilt by a board's build with that board's flags, so either is built anew.
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
if [ -d "${toolchain_dir}" ]; then
	recorded=$(jq -r '.libc // ""' "${record}" 2>/dev/null) || recorded=
	libc=$(toolchain_libc "${toolchain_dir}")
	if [ -z "${recorded}" ] || [ "${libc}" != "${recorded}" ]; then
		info "the toolchain in ${toolchain_dir} is not the one its record names: building it anew"
		rm -rf "${toolchain_dir}" "${TREE}"/build_dir/toolchain-*
	fi
fi
jobs=${WRT_JOBS:-$(nproc)}
log=$(time_log host)
status=0
BUILD_TIME_LOG="${log}" make -C "${TREE}" -j"${jobs}" tools/install toolchain/install || status=$?
time_report "${log}"
[ "${status}" -eq 0 ] || die "building the host tools and the toolchain failed"
[ -d "${toolchain_dir}" ] || die "no toolchain directory at '${toolchain_dir}'"
# toolchain/Makefile: $(call stampfile,toolchain,compile) in $(TOOLCHAIN_DIR),
# and the version stamp as its buildbot mode writes it.
make -C "${TREE}" "${toolchain_dir}/stamp/.toolchain_compile"
git -C "${TREE}" log --no-show-signature --format=%h -1 toolchain >"${toolchain_dir}/stamp/.ver_check"

# What this configuration built, or found built as recorded.
libc=$(toolchain_libc "${toolchain_dir}")
[ -n "${libc}" ] || die "the toolchain in ${toolchain_dir} has no C library"
cflags=$(make -C "${TREE}" -s val.TARGET_CFLAGS)
jq -n --arg cflags "${cflags}" --arg libc "${libc}" '{cflags: $cflags, libc: $libc}' >"${record}"
info "toolchain built with: ${cflags}"
info "toolchain ready in ${toolchain_dir}"
