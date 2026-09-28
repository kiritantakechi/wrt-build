#!/bin/sh
# Apply patches/<repo>/*.patch in filename order with git am. Stop at the first
# patch that does not apply and name it.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
require_workdir
ensure_fhs "$@"

# Fixed identity; the committer date is taken from each patch's author date
# (--committer-date-is-author-date), so the resulting commit SHAs do not depend on
# who applied the patches or when.
export GIT_COMMITTER_NAME=wrt-build GIT_COMMITTER_EMAIL=wrt-build@localhost

apply_series() {
	repo=$1 dir=$2
	for patch in "$REPO_DIR/patches/$repo"/*.patch; do
		[ -e "$patch" ] || continue
		if ! git -C "$dir" am -q --committer-date-is-author-date "$patch"; then
			git -C "$dir" am --abort 2>/dev/null || true
			die "patch does not apply: patches/$repo/$(basename -- "$patch")"
		fi
		info "applied patches/$repo/$(basename -- "$patch")"
	done
}

[ -f "$TREE/feeds.conf" ] || die "no source tree; run 'just fetch' first"
# Start from the pinned commits every time, so running this twice gives the same tree.
reset_to_lock
apply_series openwrt "$TREE"
for feed in $(lock_feeds); do
	apply_series "$feed" "$TREE/feeds/$feed"
done

cd "$TREE"
log="$WRT_WORKDIR/feeds.log"
{
	./scripts/feeds update -i -a &&
		./scripts/feeds install -a &&
		# Our own feed wins over upstream packages with the same name.
		./scripts/feeds install -a -f -p wrtbuild
} >"$log" 2>&1 || die "feeds index/install failed; see $log"
info "patched tree at $(git -C "$TREE" rev-parse HEAD)"
