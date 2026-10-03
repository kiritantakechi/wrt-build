#!/bin/sh
# patch: put the sources on the pinned commits with patches/<repo>/*.patch applied.
# Usage: scripts/patch.sh
# Each repository's patched commit is made in the object database first, then
# its work tree moves there in one checkout (build-acceleration D5): a file
# whose content the patches leave as it was keeps its modification time, so
# make rebuilds only what changed. The first patch that does not apply stops
# the step, named, before any file changes; the resulting HEAD is the same on
# every run.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
require_workdir
ensure_fhs build "$@"

[ -f "${TREE}/feeds.conf" ] || die "no source tree; run 'just fetch' first"

patch_tree openwrt "${TREE}"
# The build timestamp is the pinned commit's, whenever the patches were applied
# (scripts/get_source_date_epoch.sh reads version.date first). It is written only
# when it changes, like every other file.
epoch=$(lock_field openwrt epoch)
recorded=$(cat "${TREE}/version.date" 2>/dev/null || true)
[ "${recorded}" = "${epoch}" ] || printf '%s\n' "${epoch}" >"${TREE}/version.date"
feeds=$(lock_feeds)
for feed in ${feeds}; do
	patch_tree "${feed}" "${TREE}/feeds/${feed}"
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
