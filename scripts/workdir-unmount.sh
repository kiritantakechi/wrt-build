#!/bin/sh
# workdir-unmount: flush and unmount the build volume before the SSD is unplugged.
# Usage: scripts/workdir-unmount.sh [mountpoint]   (as root)
# The counterpart of workdir-mount; unmounting twice is a no-op. The loop device
# is released with the mount (mount -o loop sets autoclear).
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"

mountpoint=${1:-/mnt/wrt}

require_linux
uid=$(id -u)
[ "${uid}" -eq 0 ] || die "run as root"

if ! findmnt -rn --mountpoint "${mountpoint}" >/dev/null 2>&1; then
	info "${mountpoint} is not mounted"
	exit 0
fi

sync -f "${mountpoint}"
umount "${mountpoint}" || die "${mountpoint} is busy; stop the build and leave the directory first"
info "unmounted ${mountpoint}; the SSD can be unplugged"
