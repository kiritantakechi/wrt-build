#!/bin/sh
# release-sign: sign the outputs of one build for release (r4s-release-pipeline D2).
# Usage: scripts/release-sign.sh <build> <signed> --apk-key <file> --fw-key <file> [--keyring <dir>]
# Runs with the pinned signing tools only (nix run .#sign-tools -- ...), never in
# a job that builds. <build> is the unsigned output of one build: manifest.json
# and the files it lists. <signed> receives it signed:
#  - every listed file must match its sha256 in manifest.json, or nothing is signed;
#  - every package index is signed with the apk key, its build key's signature
#    dropped;
#  - every image with fwtool metadata gets a ucert chain in its trailer, a usign
#    signature under a certificate of the firmware key, as SIGN_FIRMWARE would;
#  - every signature is checked against <keyring> (default: wrt-keyring's files,
#    what the release image trusts), so a key no device trusts fails here;
#  - manifest.json gets the signed files' sha256 and is signed with the firmware
#    key (manifest.json.sig); SHA256SUMS lists every file.
# The same script signs releases with the production keys and, in the tests,
# anything with keys made for the test.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

usage() {
	die "usage: release-sign <build> <signed> --apk-key <file> --fw-key <file> [--keyring <dir>]"
}

[ "$#" -ge 2 ] || usage
build=$1
signed=$2
shift 2
apk_key=
fw_key=
keyring="${REPO_DIR}/feed/utils/wrt-keyring/files"
while [ "$#" -ge 2 ]; do
	case "$1" in
		--apk-key) apk_key=$2 ;;
		--fw-key) fw_key=$2 ;;
		--keyring) keyring=$2 ;;
		*) usage ;;
	esac
	shift 2
done
[ "$#" -eq 0 ] && [ -n "${apk_key}" ] && [ -n "${fw_key}" ] || usage
[ -f "${build}/manifest.json" ] || die "no manifest.json in ${build}"
[ ! -e "${signed}" ] || die "${signed} exists already"
# apk reads its keys directory relative to its root, /.
keyring=$(realpath "${keyring}")
apk_keys="${keyring}/etc/apk/keys"
fw_keys="${keyring}/etc/opkg/keys"

work=$(mktemp -d "${TMPDIR:-/tmp}/wrt-sign.XXXXXX")
trap 'rm -rf "${work}"' EXIT INT TERM

jq -r '.files | to_entries[] | "\(.value)  \(.key)"' "${build}/manifest.json" >"${work}/expected"
(cd "${build}" && sha256sum --check --quiet "${work}/expected") ||
	die "artifacts do not match manifest.json; nothing signed"
info "every artifact matches manifest.json"

fw_id=$(usign -F -s "${fw_key}")
[ -f "${fw_keys}/${fw_id}" ] || die "firmware key ${fw_id} is not in ${fw_keys}"
ucert -I -c "${work}/fw.ucert" -p "${fw_keys}/${fw_id}" -s "${fw_key}" ||
	die "cannot issue a certificate for firmware key ${fw_id}"

mkdir -p "${signed}"
cp -a "${build}/." "${signed}/"
jq -r '.files | keys[]' "${build}/manifest.json" >"${work}/files"

# sign_image <file>: a usign signature under the key's certificate, in the
# fwtool trailer. ucert -A reports failure after appending (it returns the
# write's true), so the verification below is what decides.
sign_image() {
	usign -S -m "$1" -s "${fw_key}" -x "${work}/image.sig"
	cp "${work}/fw.ucert" "${work}/image.ucert"
	ucert -A -c "${work}/image.ucert" -x "${work}/image.sig" || true
	fwtool -S "${work}/image.ucert" "$1"
}

while IFS= read -r file; do
	path="${signed}/${file}"
	case "${file}" in
		*/packages.adb)
			apk --allow-untrusted --sign-key "${apk_key}" adbsign --reset-signatures "${path}" ||
				die "cannot sign ${file}"
			apk --keys-dir "${apk_keys}" verify "${path}" >/dev/null ||
				die "${file} does not verify with ${apk_keys}"
			info "signed ${file}"
			;;
		*)
			fwtool -q -i /dev/null "${path}" 2>/dev/null || continue
			sign_image "${path}"
			# The chain against the firmware keys, as sysupgrade checks it
			# (fwtool_check_signature).
			rm -f "${work}/check.ucert"
			fwtool -q -s "${work}/check.ucert" "${path}" || die "${file} has no signature"
			fwtool -q -T -s /dev/null "${path}" |
				ucert -V -q -m - -c "${work}/check.ucert" -P "${fw_keys}" ||
				die "${file} does not verify with ${fw_keys}"
			info "signed ${file}"
			;;
	esac
done <"${work}/files"

# The manifest with the signed files' hashes, signed; SHA256SUMS of everything.
while IFS= read -r file; do
	sum=$(sha256sum "${signed}/${file}")
	printf '%s\t%s\n' "${file}" "${sum%% *}"
done <"${work}/files" |
	jq -R -n '[inputs | split("\t") | {(.[0]): .[1]}] | add' >"${work}/hashes"
jq --slurpfile hashes "${work}/hashes" '.files = $hashes[0]' "${build}/manifest.json" \
	>"${signed}/manifest.json"
usign -S -m "${signed}/manifest.json" -s "${fw_key}" -x "${signed}/manifest.json.sig"
usign -V -q -m "${signed}/manifest.json" -P "${fw_keys}" ||
	die "manifest.json does not verify with ${fw_keys}"
(cd "${signed}" && find . -type f | sed 's|^\./||' | sort | xargs sha256sum) >"${work}/sums"
mv "${work}/sums" "${signed}/SHA256SUMS"
info "signed release in ${signed}"
