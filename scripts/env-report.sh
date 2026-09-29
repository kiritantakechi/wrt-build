#!/bin/sh
# env-report: print the pinned host tool versions, one "name version" per line.
# Usage: scripts/env-report.sh
# The output must be identical on every host (local VM and CI), so it holds
# version numbers only: no architecture, path or build date.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
ensure_fhs test "$@"

# report <name> <command...>: the first dotted version number the command prints.
report() {
	name=$1
	shift
	version=$("$@" 2>&1 | grep -oE '[0-9]+(\.[0-9]+)+' | head -n 1)
	[ -n "${version}" ] || die "cannot read the ${name} version"
	printf '%s %s\n' "${name}" "${version}"
}

for input in nixpkgs nixpkgs-unstable; do
	rev=$(jq -er --arg i "${input}" '.nodes[$i].locked.rev' "${REPO_DIR}/flake.lock")
	printf '%s %s\n' "${input}" "${rev}"
done

# Build environment
report bash bash --version
report gcc gcc -dumpfullversion
report g++ g++ -dumpfullversion
report clang clang -dumpversion
report llc llc --version
report make make --version
report git git --version
report perl perl -e 'print $^V'
report python3 python3 --version
report tar tar --version
report gawk awk --version
report sed sed --version
report patch patch --version
report rsync rsync --version
report wget wget --version
report just just --version

# Test environment
report uv uv --version
report qemu qemu-system-aarch64 --version
report dtc dtc --version
report dumpimage dumpimage -V
report rp-pppoe pppoe -V
report radvd radvd --version
report kea-dhcp6 kea-dhcp6 -v
report dnsmasq dnsmasq --version
report iperf3 iperf3 --version
# The emulated ISP runs pppd in the sandbox (r4s-ebpf-datapath design D11).
[ -r /dev/ppp ] && [ -w /dev/ppp ] ||
	die "/dev/ppp is missing or closed to regular users: run scripts/sandbox-prepare.sh as root"
printf '%s %s\n' /dev/ppp rw

# Code standards
report shellcheck shellcheck --version
report shfmt shfmt --version
report nixfmt nixfmt --version
report actionlint actionlint -version
report editorconfig-checker editorconfig-checker -version
report gitleaks gitleaks version
