#!/bin/sh
# release-keys: create release keys and put them where they belong (r4s-release-pipeline D1, D2).
# Usage: scripts/release-keys.sh <directory> [--upload]   (on the maintainer's workstation)
# Creates an apk key (EC P-256, for package indexes) and a firmware key (usign,
# for images and manifests) in <directory>, which must not exist yet and belongs
# on the offline backup medium. Their public halves go into wrt-keyring
# (feed/utils/wrt-keyring/files), next to any key there already, so a rotation
# trusts old and new keys until the old are removed. --upload stores the private
# halves as RELEASE_APK_KEY and RELEASE_FW_KEY of the release-signing
# environment (gh secret set). The private keys are never printed and never
# enter the repository.
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"

[ "$#" -ge 1 ] || die "usage: release-keys <directory> [--upload]"
directory=$1
upload=0
[ "${2:-}" != --upload ] || upload=1
[ ! -e "${directory}" ] || die "${directory} exists already; the keys go into a new directory"
command -v usign >/dev/null || die "usign not found; run through: nix run .#sign-tools -- $0 $*"

keyring="${REPO_DIR}/feed/utils/wrt-keyring/files"
umask 077
mkdir -p "${directory}" "${keyring}/etc/apk/keys" "${keyring}/etc/opkg/keys"

openssl ecparam -name prime256v1 -genkey -noout -out "${directory}/release-apk.key"
openssl ec -in "${directory}/release-apk.key" -pubout -out "${directory}/release-apk.pem" 2>/dev/null
apk_id=$(openssl pkey -pubin -in "${directory}/release-apk.pem" -outform DER | sha256sum)
apk_id=$(printf %.8s "${apk_id}")
today=$(date -u +%Y-%m-%d)
usign -G -s "${directory}/release-fw.key" -p "${directory}/release-fw.pub" \
	-c "wrt-build release key ${today}"
fw_id=$(usign -F -p "${directory}/release-fw.pub")

umask 022
cp "${directory}/release-apk.pem" "${keyring}/etc/apk/keys/wrt-release-${apk_id}.pem"
cp "${directory}/release-fw.pub" "${keyring}/etc/opkg/keys/${fw_id}"
info "public keys added to wrt-keyring: wrt-release-${apk_id}.pem, ${fw_id}"
info "private keys in ${directory}: back them up offline, then keep them only there"

[ "${upload}" -eq 1 ] || exit 0
gh secret set RELEASE_APK_KEY --env release-signing <"${directory}/release-apk.key"
gh secret set RELEASE_FW_KEY --env release-signing <"${directory}/release-fw.key"
info "private keys stored in the release-signing environment"
