#!/bin/sh
# sandbox-prepare: open the host kernel's PPP support to the test sandbox.
# Usage: scripts/sandbox-prepare.sh   (as root; again after each VM restart)
# The emulated ISP (r4s-ebpf-datapath design D11) runs pppd as root of a user
# namespace, so the kernel needs ppp_generic and ppp_async, and /dev/ppp must be
# open to regular users. pppd still needs CAP_NET_ADMIN in its own network
# namespace to create a unit, so the device grants nothing beyond that.
# Running it twice changes nothing.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
uid=$(id -u)
[ "${uid}" -eq 0 ] || die "run as root"

modprobe -a ppp_generic ppp_async || die "the kernel has no ppp_generic or ppp_async modules"
chmod 0666 /dev/ppp
info "/dev/ppp is open to the test sandbox"
