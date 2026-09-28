#!/bin/sh
# fetch: check out the pinned upstream sources into $WRT_WORKDIR/openwrt.
# Usage: scripts/fetch.sh
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
require_workdir
ensure_fhs build "$@"

feeds=$(lock_feeds)
for name in openwrt ${feeds}; do
	sha=$(lock_field "${name}" sha)
	info "${name} @ ${sha}"
done
reset_to_lock

# Shared download cache, kept outside the tree so CI can cache it on its own.
mkdir -p "${WRT_WORKDIR}/dl"
ln -sfn "${WRT_WORKDIR}/dl" "${TREE}/dl"

# Every feed is pinned by SHA (src-git <name> <url>^<sha>); our own feed is linked.
feeds_conf="${TREE}/feeds.conf"
: >"${feeds_conf}"
for feed in ${feeds}; do
	url=$(lock_field "${feed}" url)
	sha=$(lock_field "${feed}" sha)
	printf 'src-git %s %s^%s\n' "${feed}" "${url}" "${sha}" >>"${feeds_conf}"
done
printf 'src-link wrtbuild %s\n' "${REPO_DIR}/feed" >>"${feeds_conf}"
ln -sfn "${REPO_DIR}/feed" "${TREE}/feeds/wrtbuild"

# The feeds are already at the pinned commits (scripts/feeds skips existing ^sha
# feeds, design D2); only rebuild the package indexes.
log="${WRT_WORKDIR}/feeds.log"
(cd "${TREE}" && ./scripts/feeds update -i -a) >"${log}" 2>&1 || die "feeds index failed; see ${log}"
info "sources ready in ${TREE}"
