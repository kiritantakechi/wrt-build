#!/bin/sh
# Build the configured tree and collect the outputs with a manifest.
# Expects 'just fetch', 'just patch' and 'just config <profile>' to have run.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

profile=${1:-dev}

require_linux
require_workdir
ensure_fhs "$@"

[ -f "$TREE/.config" ] || die "no .config; run 'just config $profile' first"

jobs=${WRT_JOBS:-$(nproc)}
info "make download"
make -C "$TREE" -j"$jobs" download
info "make -j$jobs ($profile)"
if ! make -C "$TREE" -j"$jobs"; then
	die "build failed; rerun 'make -C $TREE -j1 V=s' on the failing package for details"
fi

# Collect outputs and describe them. Images and the package repository of one run
# belong together: kmods only load on the kernel of the same build (vermagic).
out="$WRT_WORKDIR/out/$profile"
rm -rf "$out"
mkdir -p "$out/targets" "$out/packages"
cp -a "$TREE"/bin/targets/rockchip/armv8/. "$out/targets/"
cp -a "$TREE"/bin/packages/. "$out/packages/"
cp "$WRT_WORKDIR/out/diffconfig-$profile" "$out/diffconfig"

vermagic=$(cat "$TREE"/build_dir/target-*/linux-rockchip_armv8/linux-*/.vermagic)
kernel_version=$(cat "$TREE"/staging_dir/target-*/kernel.version 2>/dev/null || true)
sha256() { sha256sum "$1" | cut -d' ' -f1; }
{
	printf '{\n'
	printf '  "run": "%s",\n' "${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}"
	printf '  "profile": "%s",\n' "$profile"
	printf '  "upstream_lock_sha256": "%s",\n' "$(sha256 "$LOCK_FILE")"
	printf '  "patches_sha256": "%s",\n' \
		"$(cat "$REPO_DIR"/patches/*/*.patch 2>/dev/null | sha256sum | cut -d' ' -f1)"
	printf '  "openwrt_head": "%s",\n' "$(git -C "$TREE" rev-parse HEAD)"
	printf '  "kernel_version": "%s",\n' "$kernel_version"
	printf '  "vermagic": "%s",\n' "$vermagic"
	printf '  "files": {\n'
	(cd "$out" && find targets packages -type f \( -name '*.img.gz' -o -name 'packages.adb' \) | sort) |
		awk -v out="$out" 'BEGIN { first = 1 }
			{ cmd = "sha256sum \"" out "/" $0 "\""; cmd | getline line; close(cmd)
			  split(line, f, " ")
			  printf "%s    \"%s\": \"%s\"", (first ? "" : ",\n"), $0, f[1]; first = 0 }
			END { printf "\n" }'
	printf '  }\n}\n'
} >"$out/manifest.json"
jq -e . "$out/manifest.json" >/dev/null || die "manifest.json is not valid JSON"
info "outputs in $out"
