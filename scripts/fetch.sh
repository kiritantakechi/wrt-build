#!/bin/sh
# fetch: fetch the pinned upstream sources into $WRT_WORKDIR/openwrt.
# Usage: scripts/fetch.sh
# A new tree is checked out at the pinned commits; an existing one stays where it
# is until patch moves it, so that the files patch leaves as they were keep their
# modification times (build-acceleration D5).
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"
use boards upstream

require_linux
tree=$(workdir_tree)
ensure_fhs build "$@"

feeds=$(lock_feeds)
for name in openwrt ${feeds}; do
	sha=$(lock_field "${name}" sha)
	info "${name} @ ${sha}"
done
fetch_locked openwrt "${tree}"
for feed in ${feeds}; do
	fetch_locked "${feed}" "${tree}/feeds/${feed}"
done

# Shared download cache, kept outside the tree so CI can cache it on its own.
mkdir -p "${WRT_WORKDIR}/dl"
ln -sfn "${WRT_WORKDIR}/dl" "${tree}/dl"

# Every feed is pinned by SHA (src-git <name> <url>^<sha>); our own feed is linked.
feeds_conf="${tree}/feeds.conf"
: >"${feeds_conf}"
for feed in ${feeds}; do
	url=$(lock_field "${feed}" url)
	sha=$(lock_field "${feed}" sha)
	printf 'src-git %s %s^%s\n' "${feed}" "${url}" "${sha}" >>"${feeds_conf}"
done
printf 'src-link wrtbuild %s\n' "${REPO_DIR}/feed" >>"${feeds_conf}"
ln -sfn "${REPO_DIR}/feed" "${tree}/feeds/wrtbuild"
# The A/B U-Boot sources and the board table, read by uboot-rockchip, our
# uboot-wrt-qemu and the image recipe; in place before any package index is
# built, since those Makefiles include them.
mkdir -p "${tree}/env"
ln -sfn "${REPO_DIR}/uboot" "${tree}/env/uboot"
write_board_table "${tree}"

# The feeds are already at the pinned commits (scripts/feeds skips existing ^sha
# feeds, design D2); only rebuild the package indexes.
log="${WRT_WORKDIR}/feeds.log"
(cd "${tree}" && ./scripts/feeds update -i -a) >"${log}" 2>&1 || die "feeds index failed; see ${log}"
info "sources ready in ${tree}"
