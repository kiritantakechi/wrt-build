# A/B sysupgrade of the NanoPi R4S (r4s-ab-rollback design D6). sysupgrade and its
# second stage source every /lib/upgrade/*.sh in name order, so the definitions
# below replace the whole-disk ones of the rockchip platform.sh before this file.
# An upgrade writes only the slot that is not running, then makes it the trial slot.

# shellcheck source=../functions/wrt-ab.sh
. /lib/functions/wrt-ab.sh

# The second stage runs from a RAM root; take the U-Boot environment tools along.
RAMFS_COPY_BIN="${RAMFS_COPY_BIN:-} /usr/sbin/fw_printenv /usr/sbin/fw_setenv"

# wrt_ab_members <image>: print the tar members of an upgrade image, without the
# directory they sit in (sysupgrade-<board>/).
wrt_ab_members() {
	get_image "$1" | tar -tf - 2>/dev/null | grep -v '/$' | sed 's|^[^/]*/||'
}

# wrt_ab_target: print the slot an upgrade writes, the one not running.
wrt_ab_target() {
	wrt_running=$(wrt_ab_slot)
	wrt_ab_other "${wrt_running}"
}

# wrt_ab_member <image> <name>: write one member of an upgrade image to stdout.
wrt_ab_member() {
	wrt_path=$(get_image "$1" | tar -tf - | grep "/$2\$")
	get_image "$1" | tar -xOf - "${wrt_path}"
}

# wrt_ab_erofs_size <device>: print the size of the EROFS image the device starts
# with: blocks (superblock offset 36) shifted by blkszbits (offset 12).
wrt_ab_erofs_size() {
	wrt_bits=$(dd if="$1" bs=1 skip=1036 count=1 2>/dev/null | hexdump -e '1/1 "%u"')
	wrt_blocks=$(dd if="$1" bs=4 skip=265 count=1 2>/dev/null | hexdump -e '1/4 "%u"')
	echo "$((wrt_blocks << wrt_bits))"
}

# platform_check_image <image>: accept only a single-slot upgrade image, a tar of
# CONTROL, kernel (the boot partition) and root (EROFS), on a system running A/B.
platform_check_image() {
	wrt_members=$(wrt_ab_members "$1" | sort | tr '\n' ' ')
	if [ "${wrt_members}" != "CONTROL kernel root " ]; then
		echo "Not a single-slot upgrade image (members: ${wrt_members:-none})"
		return 1
	fi
	if ! wrt_ab_slot >/dev/null; then
		echo "Not running from an A/B slot; flash the factory image instead"
		return 1
	fi
}

# platform_do_upgrade <image>: write the inactive slot, give it a fresh overlay,
# and make it the slot U-Boot tries next, as a trial.
platform_do_upgrade() {
	wrt_target=$(wrt_ab_target)
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
	wrt_ab_member "$1" kernel | dd of="/dev/${wrt_boot_dev}" bs=1M conv=fsync
	wrt_ab_member "$1" root | dd of="/dev/${wrt_root_dev}" bs=1M conv=fsync

	# fstools keeps the overlay after EROFS, rounded up to 64 KiB. Clearing the
	# start of the old one makes the new system format a fresh overlay.
	wrt_overlay=$((($(wrt_ab_erofs_size "/dev/${wrt_root_dev}") + 65535) / 65536))
	dd if=/dev/zero of="/dev/${wrt_root_dev}" bs=64k seek="${wrt_overlay}" count=16 conv=fsync

	wrt_ab_setenv boot_slot "${wrt_target}" upgrade_available 1 bootcount 0
}

# platform_copy_config: hand the configuration backup to the new slot through its
# boot partition, where its preinit (79_move_config) picks it up.
platform_copy_config() {
	wrt_target=$(wrt_ab_target)
	wrt_partitions=$(wrt_ab_partitions "${wrt_target}")
	# shellcheck disable=SC2086 # the boot and root partition numbers
	set -- ${wrt_partitions}
	wrt_boot_dev=''
	if export_bootdevice && export_partdevice wrt_boot_dev "$1"; then
		mount -o rw,noatime "/dev/${wrt_boot_dev}" /mnt
		# shellcheck disable=SC2154 # set by sysupgrade
		cp -af "${UPGRADE_BACKUP}" "/mnt/${BACKUP_FILE}"
		umount /mnt
	fi
}
