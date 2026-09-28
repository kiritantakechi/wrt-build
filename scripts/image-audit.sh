#!/bin/sh
# image-audit: check a built sysupgrade image against the firmware/base-system spec.
# Usage: scripts/image-audit.sh <openwrt-...-sysupgrade.img.gz>
# Reads the image offline: partition 2 is extracted with the tree's fsck.erofs and
# the package database is queried with the tree's apk.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

image=${1:-}
[ -n "${image}" ] && [ -f "${image}" ] || die "usage: image-audit <sysupgrade.img.gz>"

require_linux
require_workdir
ensure_fhs build "$@"

host_bin="${TREE}/staging_dir/host/bin"
for tool in fsck.erofs apk; do
	[ -x "${host_bin}/${tool}" ] || die "${host_bin}/${tool} missing; build the tree first"
done

work=$(mktemp -d "${TMPDIR:-/tmp}/wrt-audit.XXXXXX")
trap 'rm -rf "${work}"' EXIT INT TERM

case "${image}" in
	*.gz)
		# sysupgrade images carry fwtool metadata after the gzip stream; gzip then
		# reports "trailing garbage ignored" with exit status 2, which is expected.
		rc=0
		gzip -dc "${image}" >"${work}/disk.img" 2>/dev/null || rc=$?
		[ "${rc}" -eq 0 ] || [ "${rc}" -eq 2 ] || die "cannot decompress ${image}"
		;;
	*) cp "${image}" "${work}/disk.img" ;;
esac

# The root filesystem is MBR partition 2: an EROFS image followed by the overlay area.
table=$(sfdisk -d "${work}/disk.img")
root_start=$(printf '%s\n' "${table}" | awk -F'[=,]' '/img2 /{ gsub(/ /, "", $2); print $2 }')
[ -n "${root_start}" ] || die "no second partition in ${image}"
dd if="${work}/disk.img" of="${work}/root.erofs" bs=512 skip="${root_start}" status=none
"${host_bin}/fsck.erofs" --extract="${work}/root" "${work}/root.erofs" >/dev/null ||
	die "partition 2 is not a readable EROFS image"
root="${work}/root"

failed=0
pass() { printf 'ok    %s\n' "$*"; }
fail() {
	printf 'FAIL  %s\n' "$*"
	failed=1
}

installed=$("${host_bin}/apk" --root "${root}" --no-network --no-cache list --installed 2>/dev/null |
	sed 's/-[0-9][^ ]* .*//')
[ -n "${installed}" ] || die "could not read the installed package list from the image"

for pkg in urngd opkg nginx nginx-ssl nginx-full uwsgi libpcre shortcut-fe natflow lrng upx; do
	if printf '%s\n' "${installed}" | grep -qx -- "${pkg}"; then
		fail "package ${pkg} is installed"
	else
		pass "package ${pkg} absent"
	fi
done
for pkg in uhttpd ucode luci-base luci-i18n-base-zh-cn zram-swap bash zsh zsh-plugins kmod-tcp-bbr; do
	if printf '%s\n' "${installed}" | grep -qx -- "${pkg}"; then
		pass "package ${pkg} installed"
	else
		fail "package ${pkg} missing"
	fi
done

# LuCI runs as a ucode CGI script under uhttpd (upstream default).
cgi=$(head -n 1 "${root}/www/cgi-bin/luci" 2>/dev/null || true)
case "${cgi}" in
	*ucode*) pass "LuCI served by uhttpd through the ucode CGI entry" ;;
	*) fail "LuCI ucode CGI entry /www/cgi-bin/luci missing" ;;
esac

upx=$(find "${root}" -type f \( -path '*/bin/*' -o -path '*/sbin/*' -o -path '*/lib/*' \) \
	-exec grep -l 'UPX!' {} + 2>/dev/null || true)
if [ -z "${upx}" ]; then pass "no UPX-packed executables"; else fail "UPX-packed files: ${upx}"; fi

root_hash=$(awk -F: '$1 == "root" { print $2 }' "${root}/etc/shadow")
if [ -z "${root_hash}" ]; then pass "no preset root password"; else fail "root has a password hash"; fi

if grep -qs '10\.0\.0\.1' "${root}/etc/board.d/99-lan-ip"; then
	pass "default LAN address 10.0.0.1"
else
	fail "default LAN address is not 10.0.0.1"
fi

[ "${failed}" -eq 0 ] || die "audit failed"
info "audit passed"
