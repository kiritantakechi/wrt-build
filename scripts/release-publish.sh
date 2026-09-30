#!/bin/sh
# release-publish: assemble a signed build into a release and publish it (r4s-release-pipeline D3).
# Usage: scripts/release-publish.sh <signed> <release> [--prerelease] [--run <number>] [--upload]
# <signed> is release-sign's output. <release> receives the release: the factory
# and upgrade images, repo.tar (the package repository as apk lays it out: the
# feeds and the target's kmods), manifest.json with its signature, SHA256SUMS of
# these, and release.json: the tag, whether it is a candidate (--prerelease), the
# notes and the assets. The tag is r<date>-<openwrt>-<run>, the run being
# $GITHUB_RUN_NUMBER unless --run names it. Nothing is assembled unless every
# image and index matches the manifest, so a release never mixes two builds.
# --upload then creates the release on GitHub (gh release create); a candidate
# never becomes the latest release.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

usage() {
	die "usage: release-publish <signed> <release> [--prerelease] [--run <number>] [--upload]"
}

[ "$#" -ge 2 ] || usage
signed=$1
release=$2
shift 2
prerelease=false
run=${GITHUB_RUN_NUMBER:-local}
upload=0
while [ "$#" -gt 0 ]; do
	case "$1" in
		--prerelease) prerelease=true ;;
		--run)
			[ "$#" -ge 2 ] || usage
			run=$2
			shift
			;;
		--upload) upload=1 ;;
		*) usage ;;
	esac
	shift
done
manifest="${signed}/manifest.json"
[ -f "${manifest}" ] && [ -f "${manifest}.sig" ] || die "${signed} is not signed (no manifest.json.sig)"
[ ! -e "${release}" ] || die "${release} exists already"

work=$(mktemp -d "${TMPDIR:-/tmp}/wrt-release.XXXXXX")
trap 'rm -rf "${work}"' EXIT INT TERM

# One build: every image and package index is the one the manifest lists.
jq -r '.files | to_entries[] | select(.key | test("^targets/.*\\.gz$|/packages\\.adb$"))
	| "\(.value)  \(.key)"' "${manifest}" >"${work}/expected"
(cd "${signed}" && sha256sum --check --quiet "${work}/expected") ||
	die "the images and the package repository are not all from the build of manifest.json"

openwrt=$(lock_field openwrt sha)
packages=$(lock_field packages sha)
luci=$(lock_field luci sha)
today=$(date -u +%Y%m%d)
short=$(printf %.7s "${openwrt}")
tag="r${today}-${short}-${run}"
mkdir -p "${release}"
for image in "${signed}"/targets/*.gz; do
	cp "${image}" "${release}/"
done
tar -cf "${release}/repo.tar" -C "${signed}" packages targets/packages
cp "${manifest}" "${manifest}.sig" "${release}/"
(cd "${release}" && sha256sum -- *) >"${work}/sums"
mv "${work}/sums" "${release}/SHA256SUMS"

notes="${work}/notes.md"
patches_sha256=$(jq -r .patches_sha256 "${manifest}")
kernel=$(jq -r .kernel_version "${manifest}")
cat >"${notes}" <<NOTES
Built from these upstream commits (upstream.lock):

- openwrt \`${openwrt}\`
- packages \`${packages}\`
- luci \`${luci}\`

Patch queue: \`${patches_sha256}\` (sha256 of patches/)
Kernel: \`${kernel}\`
NOTES
(cd "${release}" && find . -maxdepth 1 -type f | sed 's|^\./||' | sort) |
	jq -R -n --arg tag "${tag}" --argjson prerelease "${prerelease}" --rawfile notes "${notes}" \
		'{tag: $tag, prerelease: $prerelease, notes: $notes, assets: [inputs]}' >"${work}/release.json"
mv "${work}/release.json" "${release}/release.json"
info "release ${tag} assembled in ${release}"

[ "${upload}" -eq 1 ] || exit 0
set -- "${tag}" --title "${tag}" --notes-file "${notes}"
if [ "${prerelease}" = true ]; then
	set -- "$@" --prerelease --latest=false
else
	set -- "$@" --latest
fi
for asset in $(jq -r '.assets[] | select(. != "release.json")' "${release}/release.json"); do
	set -- "$@" "${release}/${asset}"
done
gh release create "$@"
info "published ${tag}"
