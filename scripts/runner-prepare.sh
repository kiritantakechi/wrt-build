#!/bin/sh
# runner-prepare: prepare a GitHub-hosted Ubuntu runner for builds and tests.
# Usage: scripts/runner-prepare.sh   (CI only; uses sudo)
#  - allow unprivileged user namespaces, which bubblewrap (the Nix FHS
#    environments) and the test sandbox need; Ubuntu 24.04 restricts them;
#  - open PPP and WireGuard to the test sandbox (sandbox-prepare.sh);
#  - make room on the root disk and create $WRT_WORKDIR on /mnt.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_linux
[ -n "${GITHUB_ACTIONS:-}" ] || die "runner-prepare changes the host; it only runs in GitHub Actions"
[ -n "${WRT_WORKDIR:-}" ] || die "WRT_WORKDIR is not set"

sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
sudo "${REPO_DIR}/scripts/sandbox-prepare.sh"
sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc /opt/hostedtoolcache/CodeQL \
	/usr/local/share/boost /usr/local/.ghcup
sudo docker image prune --all --force >/dev/null 2>&1 || true
sudo mkdir -p "${WRT_WORKDIR}"
user=$(id -u)
group=$(id -g)
sudo chown "${user}:${group}" "${WRT_WORKDIR}"
df -h / /mnt
