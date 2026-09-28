#!/bin/sh
# Loop-mount the ext4 build volume (an image file on the external SSD) inside the
# Linux VM. Run as root. Idempotent; --format creates the filesystem once and
# refuses to touch an image that already contains one.
#
#   sudo scripts/workdir-mount.sh [--format] [image] [mountpoint] [owner]
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

format=0
if [ "${1:-}" = --format ]; then
	format=1
	shift
fi
image=${1:-/mnt/mac/Volumes/SSD/wrt-work.ext4}
mnt=${2:-/mnt/wrt}
owner=${3:-${SUDO_USER:-kiritan}}

require_linux
[ "$(id -u)" -eq 0 ] || die "run as root (sudo)"
[ -f "$image" ] || die "image not found: $image (is the SSD connected?)"

if findmnt -rn --mountpoint "$mnt" >/dev/null 2>&1; then
	info "$mnt is already mounted"
	exit 0
fi

fstype=$(blkid -o value -s TYPE "$image" 2>/dev/null || true)
if [ -z "$fstype" ]; then
	[ "$format" -eq 1 ] || die "$image has no filesystem; rerun with --format to create one"
	# Lazy init and no discard: the backing file lives on HFS+, which cannot punch holes.
	mkfs.ext4 -q -L wrtwork -m 0 -E lazy_itable_init=1,lazy_journal_init=1,nodiscard "$image"
	fstype=ext4
fi
[ "$fstype" = ext4 ] || die "$image contains $fstype, expected ext4"

mkdir -p "$mnt"
mount -o loop,noatime "$image" "$mnt"
chown "$owner" "$mnt"
info "mounted $image on $mnt"
