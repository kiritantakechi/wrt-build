#!/bin/sh
# sandbox-prepare: open the host kernel's PPP and WireGuard to the test sandbox.
# Usage: scripts/sandbox-prepare.sh   (as root; again after each VM restart)
# The emulated ISP (r4s-ebpf-datapath design D11) runs pppd as root of a user
# namespace, so the kernel needs ppp_generic and ppp_async, and /dev/ppp must be
# open to regular users. pppd still needs CAP_NET_ADMIN in its own network
# namespace to create a unit, so the device grants nothing beyond that. The
# WireGuard peer (r4s-services D10) is a wireguard link in its namespace, which
# only a loaded module lets a user namespace create.
# Running it twice changes nothing.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
uid=$(id -u)
[ "${uid}" -eq 0 ] || die "run as root"

modprobe -a ppp_generic ppp_async wireguard ||
	die "the kernel lacks one of the modules ppp_generic, ppp_async and wireguard"
chmod 0666 /dev/ppp
info "/dev/ppp and WireGuard are open to the test sandbox"
