#!/bin/sh
# config-init: create the private configuration repository (r4s-release-pipeline D6).
# Usage: scripts/config-init.sh <directory>
# The repository config-push reads ($WRT_CONFIG_DIR), made from config-init.d:
# .sops.yaml naming the age recipient, secrets/secrets.enc.yaml (credentials,
# encrypted), dae/*.dae.enc (dae's configuration, encrypted: its nodes and
# subscriptions are secrets), uci/*.uci.tmpl (uci batches, filled in from the
# secrets at push time) and pods/ (Pod declarations). The age key comes from
# $SOPS_AGE_KEY_FILE (~/.config/sops/age/keys.txt by default) and is created
# there if missing: back it up offline (docs/ops.md), as nothing decrypts the
# secrets without it. Nothing is committed in plain text.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

[ "$#" -eq 1 ] || die "usage: config-init <directory>"
repo=$1
skeleton="$(dirname -- "$0")/config-init.d"
[ ! -e "${repo}" ] || die "${repo} exists already"
key=${SOPS_AGE_KEY_FILE:-${HOME}/.config/sops/age/keys.txt}
if [ ! -f "${key}" ]; then
	mkdir -p "$(dirname -- "${key}")"
	(umask 077 && age-keygen -o "${key}" 2>/dev/null)
	info "new age key in ${key}: back it up offline (docs/ops.md)"
fi
recipient=$(age-keygen -y "${key}")

mkdir -p "${repo}/pods"
cp -R "${skeleton}/secrets" "${skeleton}/dae" "${skeleton}/uci" "${repo}/"
cp "${skeleton}/gitignore" "${repo}/.gitignore"
sed "s/@recipient@/${recipient}/" "${skeleton}/sops.yaml" >"${repo}/.sops.yaml"
touch "${repo}/pods/.keep"

# encrypt <plain> <encrypted>: the skeleton's plain file becomes its encrypted
# self, for the recipient .sops.yaml names.
encrypt() {
	(cd "${repo}" && sops encrypt --filename-override "$2" /dev/stdin) <"${repo}/$1" >"${repo}/$2"
	rm "${repo}/$1"
}
encrypt secrets/secrets.yaml secrets/secrets.enc.yaml
encrypt dae/config.dae dae/config.dae.enc

git -C "${repo}" init -q
git -C "${repo}" add -A
git -C "${repo}" -c user.name=wrt-build -c user.email=wrt-build@localhost commit -q -m "wrt-config: skeleton"
info "private configuration repository in ${repo}; edit with: sops ${repo}/secrets/secrets.enc.yaml"
