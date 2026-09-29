# Bind or release the interfaces that come and go (podman0, tailscale0): dae does
# not watch for them itself (r4s-ebpf-datapath design D5).
# shellcheck disable=SC2154 # hotplug-call sets INTERFACE and ACTION
case "${INTERFACE}" in
	podman0 | tailscale0) ;;
	*) exit 0 ;;
esac
case "${ACTION}" in
	add | remove) /etc/init.d/dae running && /etc/init.d/dae reload ;;
	*) ;;
esac
