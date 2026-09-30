// Size and use of the mounted filesystems, named as node_exporter names them
// (r4s-services D8): the boot disk's overlay and the data disk above all. The
// exporter's jail sees only its own mounts, so the host's come over ubus.
const reply = ubus.call("wrt-metrics", "filesystems");

if (!reply)
	return false;

const m_size = gauge("node_filesystem_size_bytes");
const m_free = gauge("node_filesystem_free_bytes");
const m_avail = gauge("node_filesystem_avail_bytes");
const m_files = gauge("node_filesystem_files");
const m_files_free = gauge("node_filesystem_files_free");
const m_readonly = gauge("node_filesystem_readonly");

for (let fs in reply.filesystems) {
	const labels = { device: fs.device, mountpoint: fs.mountpoint, fstype: fs.fstype };
	m_size(labels, fs.size);
	m_free(labels, fs.free);
	m_avail(labels, fs.avail);
	m_files(labels, fs.files);
	m_files_free(labels, fs.files_free);
	m_readonly(labels, fs.readonly);
}
