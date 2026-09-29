#!/bin/sh
# image-audit: check a built factory image against the base system, datapath and services specs.
# Usage: scripts/image-audit.sh <openwrt-...-factory.img.gz>
# The datapath part is r4s-ebpf-datapath task 1.4: its packages, and an einat
# without libbpf or libelf. The services part: their packages, and no app that
# belongs in a container (qBittorrent, Qt, libtorrent).
# Reads the image offline: partition 2 (slot A's root) is extracted with the tree's
# fsck.erofs and the package database is queried with the tree's apk.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

image=${1:-}
[ -n "${image}" ] && [ -f "${image}" ] || die "usage: image-audit <factory.img.gz>"

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
		# Images with fwtool metadata after the gzip stream make gzip report
		# "trailing garbage ignored" with exit status 2, which is expected.
		rc=0
		gzip -dc "${image}" >"${work}/disk.img" 2>/dev/null || rc=$?
		[ "${rc}" -eq 0 ] || [ "${rc}" -eq 2 ] || die "cannot decompress ${image}"
		;;
	*) cp "${image}" "${work}/disk.img" ;;
esac

# Slot A's root filesystem is MBR partition 2: an EROFS image followed by the
# overlay area.
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

for pkg in urngd opkg nginx nginx-ssl nginx-full uwsgi libpcre shortcut-fe natflow lrng upx \
	qbittorrent qbittorrent-nox libtorrent libtorrent-rasterbar qt6-core qt5-core; do
	if printf '%s\n' "${installed}" | grep -qx -- "${pkg}"; then
		fail "package ${pkg} is installed"
	else
		pass "package ${pkg} absent"
	fi
done
for pkg in uhttpd ucode luci-base luci-i18n-base-zh-cn zram-swap bash zsh zsh-plugins kmod-tcp-bbr \
	dae luci-app-dae einat qosify kmod-sched-cake bpftool-minimal \
	kmod-usb-storage-uas kmod-fs-btrfs btrfs-progs podman crun netavark ksmbd-server \
	kmod-wireguard tailscale prometheus-node-exporter-ucode wrt-data wrt-containers wrt-metrics; do
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

# einat uses its aya loader only: no libbpf or libelf behind it.
needed=$(readelf -d "${root}/usr/bin/einat" 2>/dev/null |
	sed -n 's/.*(NEEDED).*\[\(.*\)\]$/\1/p' | tr '\n' ' ')
case "${needed}" in
	'') fail "einat missing or not a dynamic executable" ;;
	*libbpf* | *libelf*) fail "einat links ${needed}" ;;
	*) pass "einat links neither libbpf nor libelf" ;;
esac

root_hash=$(awk -F: '$1 == "root" { print $2 }' "${root}/etc/shadow")
if [ -z "${root_hash}" ]; then pass "no preset root password"; else fail "root has a password hash"; fi

if grep -qs '10\.0\.0\.1' "${root}/etc/board.d/99-lan-ip"; then
	pass "default LAN address 10.0.0.1"
else
	fail "default LAN address is not 10.0.0.1"
fi

[ "${failed}" -eq 0 ] || die "audit failed"
info "audit passed"
