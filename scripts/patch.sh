#!/bin/sh
# patch: apply patches/<repo>/*.patch on top of the pinned sources with git am.
# Usage: scripts/patch.sh
# Starts from the pinned commits every time and stops at the first patch that
# does not apply, naming it; the resulting HEAD is the same on every run.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
require_workdir
ensure_fhs build "$@"

[ -f "${TREE}/feeds.conf" ] || die "no source tree; run 'just fetch' first"

# Fixed identity; the committer date is taken from each patch's author date, so
# the resulting commit SHAs do not depend on who applied the patches or when.
export GIT_COMMITTER_NAME=wrt-build GIT_COMMITTER_EMAIL=wrt-build@localhost

# apply_series <repo> <dir>
apply_series() {
	for patch in "${REPO_DIR}/patches/$1"/*.patch; do
		[ -e "${patch}" ] || continue
		name="patches/$1/${patch##*/}"
		if ! git -C "$2" am -q --committer-date-is-author-date "${patch}"; then
			git -C "$2" am --abort 2>/dev/null || true
			die "patch does not apply: ${name}"
		fi
		info "applied ${name}"
	done
}

reset_to_lock
apply_series openwrt "${TREE}"
feeds=$(lock_feeds)
for feed in ${feeds}; do
	apply_series "${feed}" "${TREE}/feeds/${feed}"
done

# Our own feed wins over upstream packages with the same name.
log="${WRT_WORKDIR}/feeds.log"
(
	cd "${TREE}" &&
		./scripts/feeds update -i -a &&
		./scripts/feeds install -a &&
		./scripts/feeds install -a -f -p wrtbuild
) >"${log}" 2>&1 || die "feeds index/install failed; see ${log}"
head=$(git -C "${TREE}" rev-parse HEAD)
info "patched tree at ${head}"
