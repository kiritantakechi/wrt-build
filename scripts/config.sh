#!/bin/sh
# config: compose the seeds of a profile into .config and verify the result.
# Usage: scripts/config.sh [profile]   (profiles: config/profiles; default dev)
# Fails if make defconfig dropped or changed any seed line (renamed or removed
# options, unmet dependencies). Writes the diffconfig to $WRT_WORKDIR/out.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

profile=${1:-dev}

require_linux
require_workdir
ensure_fhs build "$@"

seeds=$(awk -v p="${profile}" -F: '
	/^[[:space:]]*(#|$)/ { next }
	$1 == p { print $2; found = 1 }
	END { if (!found) exit 1 }
' "${REPO_DIR}/config/profiles") || die "unknown profile '${profile}' (see config/profiles)"

[ -f "${TREE}/feeds.conf" ] || die "no source tree; run 'just fetch' and 'just patch' first"

# Rootfs overlay, kernel configuration overlay (design D7) and compiler cache live
# outside the tree; files/, env/ and .ccache are all gitignored upstream.
ln -sfn "${REPO_DIR}/files" "${TREE}/files"
mkdir -p "${TREE}/env" "${WRT_WORKDIR}/ccache" "${WRT_WORKDIR}/out"
ln -sfn "${REPO_DIR}/config/kernel.config" "${TREE}/env/kernel-config"
ln -sfn "${WRT_WORKDIR}/ccache" "${TREE}/.ccache"

wanted="${WRT_WORKDIR}/out/seed-${profile}.config"
: >"${wanted}"
for seed in ${seeds}; do
	file="${REPO_DIR}/config/${seed}.seed"
	[ -f "${file}" ] || die "missing seed file config/${seed}.seed"
	cat "${file}" >>"${wanted}"
done

cp "${wanted}" "${TREE}/.config"
info "make defconfig (${profile}:${seeds})"
make -C "${TREE}" defconfig >/dev/null

missing=$(missing_config_lines "${wanted}" "${TREE}/.config")
if [ -n "${missing}" ]; then
	printf 'error: defconfig dropped or changed these seed lines:\n%s\n' "${missing}" >&2
	exit 1
fi

diffconfig="${WRT_WORKDIR}/out/diffconfig-${profile}"
(cd "${TREE}" && ./scripts/diffconfig.sh) >"${diffconfig}" 2>/dev/null || die "scripts/diffconfig.sh failed"
info "config ok; diffconfig in ${diffconfig}"
