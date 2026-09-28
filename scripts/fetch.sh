#!/bin/sh
# Check out the pinned upstream sources into $WRT_WORKDIR/openwrt.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
require_workdir
ensure_fhs "$@"

info "openwrt @ $(lock_field openwrt sha)"
for feed in $(lock_feeds); do
	info "feed $feed @ $(lock_field "$feed" sha)"
done
reset_to_lock

# Shared download cache, kept outside the tree so CI can cache it on its own.
mkdir -p "$WRT_WORKDIR/dl"
ln -sfn "$WRT_WORKDIR/dl" "$TREE/dl"

feeds_conf="$TREE/feeds.conf"
: >"$feeds_conf"
for feed in $(lock_feeds); do
	printf 'src-git %s %s^%s\n' "$feed" "$(lock_field "$feed" url)" "$(lock_field "$feed" sha)" >>"$feeds_conf"
done
printf 'src-link wrtbuild %s\n' "$REPO_DIR/feed" >>"$feeds_conf"
ln -sfn "$REPO_DIR/feed" "$TREE/feeds/wrtbuild"

# The feeds are already at the pinned commits; only rebuild the package indexes.
cd "$TREE"
log="$WRT_WORKDIR/feeds.log"
./scripts/feeds update -i -a >"$log" 2>&1 || die "feeds index failed; see $log"
info "sources ready in $TREE"
