#!/bin/sh
# workdir-mount: loop-mount the ext4 build volume inside the Linux VM.
# Usage: scripts/workdir-mount.sh [--format] [image] [mountpoint]   (as root)
# The image file lives on the external SSD (design D9). Mounting twice is a no-op;
# --format creates the filesystem once and refuses an image that already has one.
# The mountpoint is handed to the owner of this repository.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

format=0
if [ "${1:-}" = --format ]; then
	format=1
	shift
fi
image=${1:-/mnt/mac/Volumes/SSD/wrt-work.ext4}
mountpoint=${2:-/mnt/wrt}

require_linux
uid=$(id -u)
[ "${uid}" -eq 0 ] || die "run as root"
[ -f "${image}" ] || die "image not found: ${image} (is the SSD connected?)"

if findmnt -rn --mountpoint "${mountpoint}" >/dev/null 2>&1; then
	info "${mountpoint} is already mounted"
	exit 0
fi

fstype=$(blkid -o value -s TYPE "${image}" 2>/dev/null || true)
if [ -z "${fstype}" ]; then
	[ "${format}" -eq 1 ] || die "${image} has no filesystem; rerun with --format to create one"
	# Lazy init and no discard: the backing file lives on HFS+, which cannot punch holes.
	mkfs.ext4 -q -L wrtwork -m 0 -E lazy_itable_init=1,lazy_journal_init=1,nodiscard "${image}"
	fstype=ext4
fi
[ "${fstype}" = ext4 ] || die "${image} contains ${fstype}, expected ext4"

owner=$(stat -c %u:%g "${REPO_DIR}")
mkdir -p "${mountpoint}"
mount -o loop,noatime "${image}" "${mountpoint}"
chown "${owner}" "${mountpoint}"
info "mounted ${image} on ${mountpoint}"
