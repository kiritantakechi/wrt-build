# A/B sysupgrade (r4s-ab-rollback design D6). sysupgrade and its
# second stage source every /lib/upgrade/*.sh in name order, so the definitions
# below replace the whole-disk ones of the rockchip platform.sh before this file.
# An upgrade writes only the slot that is not running, then makes it the trial slot.

# shellcheck source=../functions/wrt-ab.sh
. /lib/functions/wrt-ab.sh

# The second stage runs from a RAM root; take the U-Boot environment tools along.
RAMFS_COPY_BIN="${RAMFS_COPY_BIN:-} /usr/sbin/fw_printenv /usr/sbin/fw_setenv"

# wrt_ab_members <image>: print the files of an upgrade image's tar, sorted, as
# the archive names them: <dir>/<member>.
wrt_ab_members() {
	get_image "$1" | tar -tf - 2>/dev/null | grep -v '/$' | sort
}

# wrt_ab_dir <image>: print the directory an upgrade image's members sit in
# (sysupgrade-<board>), when they are exactly CONTROL, kernel and root of one
# directory; the check and the write read the same names.
wrt_ab_dir() {
	wrt_listed=$(wrt_ab_members "$1")
	wrt_dir=${wrt_listed%%/*}
	[ -n "${wrt_dir}" ] &&
		[ "${wrt_listed}" = "$(printf '%s/CONTROL\n%s/kernel\n%s/root' "${wrt_dir}" "${wrt_dir}" "${wrt_dir}")" ] &&
		echo "${wrt_dir}"
}

# wrt_ab_member <image> <dir> <name>: write one member of an upgrade image to
# stdout; fails when the image cannot be read to the member's end.
wrt_ab_member() {
	get_image "$1" | tar -xOf - "$2/$3"
}

# wrt_ab_write <image> <dir> <name> <device>: write one member of an upgrade
# image to a device. pipefail: a member that cannot be read fails the write as a
# device that cannot be written does.
wrt_ab_write() {
	(
		# shellcheck disable=SC3040 # POSIX.1-2024; busybox ash has it
		set -o pipefail
		wrt_ab_member "$1" "$2" "$3" | dd of="$4" bs=1M conv=fsync
	)
}

# wrt_ab_copy_config <boot device>: put the configuration backup on the new
# slot's boot partition, where its preinit (79_move_config) picks it up.
wrt_ab_copy_config() {
	mount -o rw,noatime "/dev/$1" /mnt || return 1
	# shellcheck disable=SC2154 # set by sysupgrade
	cp -af "${UPGRADE_BACKUP}" "/mnt/${BACKUP_FILE}" && sync
	wrt_copied=$?
	umount /mnt || return 1
	return "${wrt_copied}"
}

# wrt_ab_erofs_size <device>: print the size of the EROFS image the device starts
# with: blocks (superblock offset 36) shifted by blkszbits (offset 12).
wrt_ab_erofs_size() {
	wrt_bits=$(dd if="$1" bs=1 skip=1036 count=1 2>/dev/null | hexdump -e '1/1 "%u"')
	wrt_blocks=$(dd if="$1" bs=4 skip=265 count=1 2>/dev/null | hexdump -e '1/4 "%u"')
	echo "$((wrt_blocks << wrt_bits))"
}

# platform_check_image <image>: accept only a single-slot upgrade image, a tar of
# CONTROL, kernel (the boot partition) and root (EROFS), on a system running A/B
# that can write the U-Boot environment where its bootloader reads it: one
# whose bootloader named no environment has none configured (31-wrt-ab), and
# refuses before anything is written (trial-boot-resilience D3).
platform_check_image() {
	if ! wrt_ab_dir "$1" >/dev/null; then
		wrt_listed=$(wrt_ab_members "$1" | tr '\n' ' ') || wrt_listed=
		echo "Not a single-slot upgrade image (members: ${wrt_listed:-none})"
		return 1
	fi
	if ! wrt_ab_slot >/dev/null; then
		echo "Not running from an A/B slot; flash the factory image instead"
		return 1
	fi
	if ! fw_printenv >/dev/null 2>&1; then
		echo "The bootloader names no U-Boot environment; flash the factory image instead"
		return 1
	fi
}

# platform_do_upgrade <image>: write the inactive slot, give it a fresh overlay
# and the configuration backup (sysupgrade's UPGRADE_BACKUP), and only once all
# of it is written, make it the slot U-Boot tries next, as a trial. Stage 2
# reboots whatever this returns: after a failure, into the running slot
# (device-integrity D2).
platform_do_upgrade() {
	wrt_dir=$(wrt_ab_dir "$1") || {
		echo "Not a single-slot upgrade image"
		return 1
	}
	wrt_running=$(wrt_ab_slot) || {
		echo "Not running from an A/B slot"
		return 1
	}
	wrt_target=$(wrt_ab_other "${wrt_running}")
	wrt_partitions=$(wrt_ab_partitions "${wrt_target}")
	# shellcheck disable=SC2086 # the boot and root partition numbers
	set -- "$1" ${wrt_partitions}
	wrt_boot_dev='' wrt_root_dev=''
	if ! export_bootdevice ||
		! export_partdevice wrt_boot_dev "$2" ||
		! export_partdevice wrt_root_dev "$3"; then
		echo "Unable to find the partitions of slot ${wrt_target}"
		return 1
	fi

	v "Writing slot ${wrt_target} to /dev/${wrt_boot_dev} and /dev/${wrt_root_dev}..."
	if ! wrt_ab_write "$1" "${wrt_dir}" kernel "/dev/${wrt_boot_dev}" ||
		! wrt_ab_write "$1" "${wrt_dir}" root "/dev/${wrt_root_dev}"; then
		echo "Writing slot ${wrt_target} failed; slot ${wrt_running} stays"
		return 1
	fi

	# fstools keeps the overlay after EROFS, rounded up to 64 KiB. Clearing the
	# start of the old one makes the new system format a fresh overlay.
	wrt_overlay=$((($(wrt_ab_erofs_size "/dev/${wrt_root_dev}") + 65535) / 65536))
	if ! dd if=/dev/zero of="/dev/${wrt_root_dev}" bs=64k seek="${wrt_overlay}" count=16 conv=fsync; then
		echo "Clearing the overlay of slot ${wrt_target} failed; slot ${wrt_running} stays"
		return 1
	fi

	# The configuration before the switch: a power cut in between must not boot
	# the new slot without it.
	if [ -n "${UPGRADE_BACKUP:-}" ] && ! wrt_ab_copy_config "${wrt_boot_dev}"; then
		echo "Copying the configuration to slot ${wrt_target} failed; slot ${wrt_running} stays"
		return 1
	fi

	wrt_ab_setenv boot_slot "${wrt_target}" upgrade_available 1 bootcount 0
}

# platform_copy_config: platform_do_upgrade has put the configuration on the new
# slot already, before the switch; this replaces the platform's whole-disk copy.
platform_copy_config() {
	:
}
