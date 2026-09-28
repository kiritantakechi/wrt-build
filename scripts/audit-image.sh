#!/bin/sh
# Audit a built sysupgrade image against the firmware/base-system spec.
# Usage: scripts/audit-image.sh <openwrt-...-sysupgrade.img.gz>
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

image=${1:-}
[ -n "$image" ] && [ -f "$image" ] || die "usage: audit-image <sysupgrade.img.gz>"

require_linux
require_workdir
ensure_fhs "$@"

host_bin="$TREE/staging_dir/host/bin"
for tool in fsck.erofs apk; do
	[ -x "$host_bin/$tool" ] || die "$host_bin/$tool missing; build the tree first"
done

work=$(mktemp -d "${TMPDIR:-/tmp}/wrt-audit.XXXXXX")
trap 'rm -rf "$work"' EXIT INT TERM

case "$image" in
*.gz)
	# sysupgrade images carry fwtool metadata after the gzip stream; gzip then
	# reports "trailing garbage ignored" with exit status 2, which is expected.
	rc=0
	gzip -dc "$image" >"$work/disk.img" 2>/dev/null || rc=$?
	[ "$rc" -eq 0 ] || [ "$rc" -eq 2 ] || die "cannot decompress $image"
	;;
*) cp "$image" "$work/disk.img" ;;
esac

# Root filesystem is MBR partition 2: an EROFS image followed by the overlay area.
root_start=$(sfdisk -d "$work/disk.img" | awk -F'[=,]' '/img2 /{gsub(/ /,"",$2); print $2}')
[ -n "$root_start" ] || die "no second partition in $image"
dd if="$work/disk.img" of="$work/root.erofs" bs=512 skip="$root_start" status=none
"$host_bin/fsck.erofs" --extract="$work/root" "$work/root.erofs" >/dev/null ||
	die "partition 2 is not a readable EROFS image"
root="$work/root"

fail=0
pass() { printf 'ok    %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fail=1; }

installed=$("$host_bin/apk" --root "$root" --no-network --no-cache list --installed 2>/dev/null |
	sed 's/-[0-9][^ ]* .*//')
[ -n "$installed" ] || die "could not read the installed package list from the image"
has_pkg() { printf '%s\n' "$installed" | grep -qx -- "$1"; }

for pkg in urngd opkg nginx nginx-ssl nginx-full uwsgi libpcre shortcut-fe natflow lrng upx; do
	if has_pkg "$pkg"; then bad "package $pkg is installed"; else pass "package $pkg absent"; fi
done
for pkg in uhttpd ucode luci-base luci-i18n-base-zh-cn zram-swap zsh zsh-plugins kmod-tcp-bbr; do
	if has_pkg "$pkg"; then pass "package $pkg installed"; else bad "package $pkg missing"; fi
done

# LuCI runs as a ucode CGI script under uhttpd (upstream default).
if head -n 1 "$root/www/cgi-bin/luci" 2>/dev/null | grep -q ucode; then
	pass "LuCI served by uhttpd through the ucode CGI entry"
else
	bad "LuCI ucode CGI entry /www/cgi-bin/luci missing"
fi

upx=$(find "$root" -type f \( -path '*/bin/*' -o -path '*/sbin/*' -o -path '*/lib/*' \) \
	-exec grep -l 'UPX!' {} + 2>/dev/null || true)
if [ -n "$upx" ]; then bad "UPX-packed files: $upx"; else pass "no UPX-packed executables"; fi

root_hash=$(awk -F: '$1 == "root" { print $2 }' "$root/etc/shadow")
if [ -z "$root_hash" ]; then pass "no preset root password"; else bad "root has a password hash"; fi

if [ -e "$root/etc/board.d/99-lan-ip" ] && grep -q '10.0.0.1' "$root/etc/board.d/99-lan-ip"; then
	pass "default LAN address 10.0.0.1"
else
	bad "default LAN address is not 10.0.0.1"
fi

if [ "$fail" -eq 0 ]; then
	info "audit passed"
else
	info "audit failed"
fi
exit "$fail"
