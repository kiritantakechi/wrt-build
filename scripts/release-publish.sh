#!/bin/sh
# release-publish: assemble every board's signed build into one release and publish it (r4s-release-pipeline D3, board-model D10).
# Usage: scripts/release-publish.sh <signed> <release> [--boards <id>,...] [--prerelease] [--run <number>] [--upload]
# <signed> holds each board's signed build, release-sign's output, in a directory
# named after the board: every board of boards/, or exactly those --boards names,
# so that no board's devices are left without their set. <release> receives the
# release: each board's factory and upgrade images, which carry its device's
# name; its package repository as apk lays it out (the feeds and the target's
# kmods) and its manifest.json with the signature, named after its device
# (<device>-repo.tar, <device>-manifest.json, <device>-manifest.json.sig);
# SHA256SUMS of all these; and release.json: the tag, whether it is a candidate
# (--prerelease), the notes, the boards and the assets. The images are links to
# the signed builds' where the file system allows. The tag is
# r<date>-<openwrt>-<run>, the run being $GITHUB_RUN_NUMBER
# unless --run names it. Nothing is assembled unless every image and index of a
# board matches its manifest, and every board was built from the same sources
# (upstream.lock, patches and upstream commit), so a release never mixes builds.
# --upload then creates the release on GitHub (gh release create); a candidate
# never becomes the latest release.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

usage() {
	die "usage: release-publish <signed> <release> [--boards <id>,...] [--prerelease] [--run <number>] [--upload]"
}

# place <file> <directory>: put <file> into <directory> as a link, or as a copy
# on another file system; a release is assembled once and never changed.
place() {
	ln "$1" "$2/" 2>/dev/null || cp "$1" "$2/"
}

[ "$#" -ge 2 ] || usage
signed=$1
release=$2
shift 2
wanted=$(board_ids)
prerelease=false
run=${GITHUB_RUN_NUMBER:-local}
upload=0
while [ "$#" -gt 0 ]; do
	case "$1" in
		--boards)
			[ "$#" -ge 2 ] || usage
			wanted=$(printf '%s\n' "$2" | tr ',' '\n')
			shift
			;;
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
[ ! -e "${release}" ] || die "${release} exists already"

work=$(mktemp -d "${TMPDIR:-/tmp}/wrt-release.XXXXXX")
trap 'rm -rf "${work}"' EXIT INT TERM

# Each board's build is one build: every image and package index is the one its
# manifest lists.
boards=
for build in "${signed}"/*/; do
	[ -d "${build}" ] || continue
	build=${build%/}
	board=${build##*/}
	device=$(board_field "${board}" .device)
	manifest="${build}/manifest.json"
	[ -f "${manifest}" ] && [ -f "${manifest}.sig" ] || die "${build} is not signed (no manifest.json.sig)"
	built=$(jq -r '"\(.board) \(.device)"' "${manifest}")
	[ "${built}" = "${board} ${device}" ] ||
		die "${build} holds the build of ${built}, not of ${board} ${device}"
	jq -r '.files | to_entries[] | select(.key | test("^targets/.*\\.gz$|/packages\\.adb$"))
		| "\(.value)  \(.key)"' "${manifest}" >"${work}/expected"
	(cd "${build}" && sha256sum --check --quiet "${work}/expected") ||
		die "the images and the package repository of ${board} are not all from the build of its manifest.json"
	boards="${boards:+${boards} }${board}"
done
[ -n "${boards}" ] || die "no signed builds in ${signed}"
for board in ${wanted}; do
	board_field "${board}" .device >/dev/null
done
held=$(printf '%s\n' "${boards}" | tr ' ' '\n' | sort | tr '\n' ' ')
asked=$(printf '%s\n' "${wanted}" | sort | tr '\n' ' ')
[ "${held}" = "${asked}" ] ||
	die "the release is of ${asked% }, but ${signed} holds the builds of ${held% }"

# The boards' builds come from the same sources.
first=${boards%% *}
for board in ${boards}; do
	for field in upstream_lock_sha256 patches_sha256 openwrt_head; do
		ours=$(jq -r ".${field}" "${signed}/${first}/manifest.json")
		theirs=$(jq -r ".${field}" "${signed}/${board}/manifest.json")
		[ "${theirs}" = "${ours}" ] ||
			die "${first} and ${board} were built from different sources: their ${field} differs"
	done
done

openwrt=$(lock_field openwrt sha)
packages=$(lock_field packages sha)
luci=$(lock_field luci sha)
today=$(date -u +%Y%m%d)
short=$(printf %.7s "${openwrt}")
tag="r${today}-${short}-${run}"
mkdir -p "${release}"
for board in ${boards}; do
	build="${signed}/${board}"
	device=$(board_field "${board}" .device)
	for image in "${build}"/targets/*.gz; do
		[ ! -e "${release}/${image##*/}" ] || die "two boards have an image named ${image##*/}"
		place "${image}" "${release}"
	done
	tar -cf "${release}/${device}-repo.tar" -C "${build}" packages targets/packages
	cp "${build}/manifest.json" "${release}/${device}-manifest.json"
	cp "${build}/manifest.json.sig" "${release}/${device}-manifest.json.sig"
done
(cd "${release}" && sha256sum -- *) >"${work}/sums"
mv "${work}/sums" "${release}/SHA256SUMS"

notes="${work}/notes.md"
patches_sha256=$(jq -r .patches_sha256 "${signed}/${first}/manifest.json")
kernel=$(jq -r .kernel_version "${signed}/${first}/manifest.json")
cat >"${notes}" <<NOTES
Built from these upstream commits (upstream.lock):

- openwrt \`${openwrt}\`
- packages \`${packages}\`
- luci \`${luci}\`

Patch queue: \`${patches_sha256}\` (sha256 of patches/)
Kernel: \`${kernel}\`
Boards: ${boards}
NOTES
(cd "${release}" && find . -maxdepth 1 -type f | sed 's|^\./||' | sort) |
	jq -R -n --arg tag "${tag}" --argjson prerelease "${prerelease}" --rawfile notes "${notes}" \
		--arg boards "${boards}" \
		'{tag: $tag, prerelease: $prerelease, notes: $notes, boards: ($boards | split(" ")),
		assets: [inputs]}' >"${work}/release.json"
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
