# The USB data disk (r4s-services D1): btrfs, its top level mounted by UUID at
# /mnt/data, and the subvolumes at fixed paths in it. Services that keep their
# data there start only while it is mounted: its paths are otherwise plain
# directories on the boot disk.
# shellcheck shell=sh disable=SC2034 # for the scripts that source this

WRT_DATA=/mnt/data
WRT_DATA_LABEL=wrtdata
WRT_DATA_SUBVOLUMES="containers downloads shares logs"
WRT_DATA_OPTIONS=compress=zstd:3,noatime,space_cache=v2
# The data disk's line in /proc/mounts.
WRT_DATA_MOUNT=" ${WRT_DATA} btrfs "

# wrt_data_mounted: whether the data disk is mounted at /mnt/data.
wrt_data_mounted() {
	grep -q "${WRT_DATA_MOUNT}" /proc/mounts
}
