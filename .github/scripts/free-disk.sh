#!/bin/sh
# Make room on a GitHub-hosted ubuntu runner and create $WRT_WORKDIR on /mnt.
set -eu
sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc /opt/hostedtoolcache/CodeQL \
	/usr/local/share/boost /usr/local/.ghcup
sudo docker image prune --all --force >/dev/null 2>&1 || true
sudo mkdir -p "$WRT_WORKDIR"
sudo chown "$(id -u):$(id -g)" "$WRT_WORKDIR"
df -h / /mnt
