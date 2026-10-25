# Bind or release the interfaces that come and go (podman0, tailscale0): dae does
# not watch for them itself (r4s-ebpf-datapath design D5). In the background: a
# reload waits while dae turns it away, as while it starts, and the hotplug
# queue must not wait with it (device-integrity D5).
# shellcheck disable=SC2154 # hotplug-call sets INTERFACE and ACTION
case "${INTERFACE}" in
	podman0 | tailscale0) ;;
	*) exit 0 ;;
esac
case "${ACTION}" in
	add | remove) { /etc/init.d/dae running && /etc/init.d/dae reload; } >/dev/null 2>&1 & ;;
	*) ;;
esac
