#!/bin/sh
# workdir-mount: loop-mount the ext4 build volume inside the Linux VM.
# Usage: scripts/workdir-mount.sh [--format [--owner user]] [image] [mountpoint]   (as root)
# The image file lives on the external SSD (design D9). Mounting twice is a no-op.
# --format creates the filesystem once (never over one) and gives its top
# directory to --owner, else to sudo's caller, else to the owner of this
# repository. The filesystem keeps its owner, so a later mount changes nothing:
# OrbStack shows the Mac's files as owned by whoever reads them, root included.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

format=0
owner=
while [ "$#" -gt 0 ]; do
	case "$1" in
		--format) format=1 ;;
		--owner)
			user=$(id -u "$2") || die "no user $2"
			group=$(id -g "$2")
			owner=${user}:${group}
			shift
			;;
		*) break ;;
	esac
	shift
done
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
created=0
if [ -z "${fstype}" ]; then
	[ "${format}" -eq 1 ] || die "${image} has no filesystem; rerun with --format to create one"
	[ -n "${owner}" ] || owner=${SUDO_UID:+${SUDO_UID}:${SUDO_GID}}
	[ -n "${owner}" ] || owner=$(stat -c %u:%g "${REPO_DIR}")
	[ "${owner%%:*}" -ne 0 ] || die "cannot tell whose the volume is; rerun with --owner <user>"
	# Lazy init and no discard: the backing file lives on HFS+, which cannot punch holes.
	mkfs.ext4 -q -L wrtwork -m 0 -E lazy_itable_init=1,lazy_journal_init=1,nodiscard "${image}"
	fstype=ext4
	created=1
fi
[ "${fstype}" = ext4 ] || die "${image} contains ${fstype}, expected ext4"

mkdir -p "${mountpoint}"
mount -o loop,noatime "${image}" "${mountpoint}"
# Direct I/O: the image already sits in the host's page cache, so the loop
# device reads and writes it without keeping a second copy in this system's.
loop=$(findmnt -rno SOURCE --mountpoint "${mountpoint}")
losetup --direct-io=on "${loop}"
[ "${created}" -eq 0 ] || chown "${owner}" "${mountpoint}"
info "mounted ${image} on ${mountpoint}"
