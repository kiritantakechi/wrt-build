#!/bin/sh
# Compose config/<seed>.seed files for a profile, run make defconfig, and fail if
# defconfig dropped or changed any line from the seeds (renamed or removed
# options, unmet dependencies). Writes the resulting diffconfig to $WRT_WORKDIR/out.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

profile=${1:-dev}

require_linux
require_workdir
ensure_fhs build "$@"

seeds=$(awk -v p="$profile" -F: '
	/^[[:space:]]*(#|$)/ { next }
	$1 == p { print $2; found = 1 }
	END { if (!found) exit 1 }
' "$REPO_DIR/config/profiles") || die "unknown profile '$profile' (see config/profiles)"

[ -f "$TREE/feeds.conf" ] || die "no source tree; run 'just fetch' and 'just patch' first"

# Rootfs overlay and compiler cache live outside the tree (both are gitignored upstream).
ln -sfn "$REPO_DIR/files" "$TREE/files"
mkdir -p "$WRT_WORKDIR/ccache" "$WRT_WORKDIR/out"
ln -sfn "$WRT_WORKDIR/ccache" "$TREE/.ccache"

wanted="$WRT_WORKDIR/out/seed-$profile.config"
: >"$wanted"
for seed in $seeds; do
	file="$REPO_DIR/config/$seed.seed"
	[ -f "$file" ] || die "missing seed file config/$seed.seed"
	cat "$file" >>"$wanted"
done

cp "$wanted" "$TREE/.config"
info "make defconfig ($profile: $seeds)"
make -C "$TREE" defconfig >/dev/null

# Every option line of the seeds must survive defconfig unchanged.
missing=$(grep -E '^(CONFIG_|# CONFIG_[A-Za-z0-9_]+ is not set)' "$wanted" |
	while IFS= read -r line; do
		grep -Fxq -- "$line" "$TREE/.config" || printf '  %s\n' "$line"
	done)
if [ -n "$missing" ]; then
	printf 'error: defconfig dropped or changed these seed lines:\n%s\n' "$missing" >&2
	exit 1
fi

(cd "$TREE" && ./scripts/diffconfig.sh) >"$WRT_WORKDIR/out/diffconfig-$profile" 2>/dev/null ||
	die "scripts/diffconfig.sh failed"
info "config ok; diffconfig in $WRT_WORKDIR/out/diffconfig-$profile"
