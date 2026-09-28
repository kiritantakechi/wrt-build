#!/bin/sh
# Prepare a GitHub-hosted ubuntu runner for the build:
#  - allow unprivileged user namespaces, which the Nix FHS environment
#    (bubblewrap) needs; Ubuntu 24.04 restricts them through AppArmor;
#  - make room on the root disk and create $WRT_WORKDIR on /mnt.
set -eu
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc /opt/hostedtoolcache/CodeQL \
	/usr/local/share/boost /usr/local/.ghcup
sudo docker image prune --all --force >/dev/null 2>&1 || true
sudo mkdir -p "$WRT_WORKDIR"
sudo chown "$(id -u):$(id -g)" "$WRT_WORKDIR"
df -h / /mnt
