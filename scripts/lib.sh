# Shared helpers for the build scripts. POSIX sh; source it, do not execute it.

REPO_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
LOCK_FILE="$REPO_DIR/upstream.lock"

die() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

info() {
	printf '==> %s\n' "$*" >&2
}

# Fail before anything touches the filesystem when the host cannot build:
# BTF (pahole) and mold are unavailable on macOS hosts.
require_linux() {
	[ "$(uname -s)" = Linux ] ||
		die "builds run only on Linux; use the OrbStack NixOS VM or CI (see docs/dev-setup.md)"
}

# The build tree lives outside the repository.
require_workdir() {
	[ -n "${WRT_WORKDIR:-}" ] || die "WRT_WORKDIR is not set (see docs/dev-setup.md)"
	[ -d "$WRT_WORKDIR" ] || die "WRT_WORKDIR does not exist: $WRT_WORKDIR"
	case "$WRT_WORKDIR" in
	"$REPO_DIR" | "$REPO_DIR"/*) die "WRT_WORKDIR must be outside the repository" ;;
	esac
	TREE="$WRT_WORKDIR/openwrt"
}

# Re-execute the calling script inside the Nix FHS environment unless already there.
ensure_fhs() {
	[ -n "${WRT_FHS:-}" ] && return 0
	command -v wrt-fhs >/dev/null 2>&1 ||
		die "not inside the build environment; run through 'nix develop' (see docs/dev-setup.md)"
	# shellcheck disable=SC2016 # expanded by the inner shell, not here
	exec wrt-fhs -c 'exec "$0" "$@"' "$0" "$@"
}

# lock_field <name> <field>: field is url, sha or epoch.
lock_field() {
	awk -v name="$1" -v field="$2" '
		/^[[:space:]]*(#|$)/ { next }
		$1 == name {
			if (field == "url") print $2
			else if (field == "sha") print $3
			else if (field == "epoch") print $4
			found = 1
		}
		END { if (!found) exit 1 }
	' "$LOCK_FILE" || die "upstream.lock has no entry for '$1'"
}

# Put the openwrt tree and every feed back on its pinned commit (dropping applied
# patches) and restore version.date, which git clean removes.
reset_to_lock() {
	git_checkout_sha "$TREE" "$(lock_field openwrt url)" "$(lock_field openwrt sha)"
	# Build timestamp comes from the pinned commit, not from when patches were
	# applied (scripts/get_source_date_epoch.sh reads version.date first).
	lock_field openwrt epoch >"$TREE/version.date"
	for feed in $(lock_feeds); do
		git_checkout_sha "$TREE/feeds/$feed" "$(lock_field "$feed" url)" "$(lock_field "$feed" sha)"
	done
}

# Feed names in lock order (everything except openwrt itself).
lock_feeds() {
	awk '/^[[:space:]]*(#|$)/ { next } $1 != "openwrt" { print $1 }' "$LOCK_FILE"
}

# git_checkout_sha <dir> <url> <sha>: shallow-fetch exactly <sha> and check it out
# detached, discarding local commits (e.g. previously applied patches).
git_checkout_sha() {
	dir=$1 url=$2 sha=$3
	if [ ! -d "$dir/.git" ]; then
		mkdir -p "$dir"
		git -C "$dir" init -q
		git -C "$dir" remote add origin "$url"
	fi
	git -C "$dir" remote set-url origin "$url"
	if ! git -C "$dir" cat-file -e "$sha^{commit}" 2>/dev/null; then
		git -C "$dir" fetch -q --depth 1 origin "$sha"
	fi
	git -C "$dir" -c advice.detachedHead=false checkout -q -f --detach "$sha"
	# Files added by earlier patch runs are untracked now; drop them so git am can
	# re-add them. Ignored build output (dl/, build_dir/, feeds/, .config) is kept.
	git -C "$dir" clean -q -f -d
	[ "$(git -C "$dir" rev-parse HEAD)" = "$sha" ] || die "$dir is not at $sha"
}
