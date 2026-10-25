# wrt-sync: what wrt-sync and wrt-update share (r4s-release-pipeline D4). POSIX
# sh, so no locals: every function keeps its variables under a wrt_ prefix.

# wrt_sync_device: print the router's OpenWrt device, after which a release
# names the router's asset set (board-model D10).
wrt_sync_device() {
	tr ',' '_' </tmp/sysinfo/board_name
}
