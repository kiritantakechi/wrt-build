#!/bin/sh
# udhcpc event script for the LAN clients of the test sandbox: configure the
# leased address and default route, and nothing else (no resolv.conf).
set -eu

case "${1:-}" in
	bound | renew)
		ip -4 addr flush dev "${interface:?}"
		ip -4 addr add "${ip:?}/${subnet:?}" dev "${interface}"
		if [ -n "${router:-}" ]; then
			ip -4 route replace default via "${router%% *}" dev "${interface}"
		fi
		;;
	deconfig) ip -4 addr flush dev "${interface:?}" ;;
	*) ;;
esac
