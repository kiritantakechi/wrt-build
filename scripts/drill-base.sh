#!/bin/sh
# drill-base: prepare the image the upgrade drill starts from (r4s-release-pipeline D5).
# Usage: scripts/drill-base.sh
# out/drill-base gets the factory image of the latest stable release on GitHub,
# or, before the first release, this build's own (out/ci), with this build's
# emulator firmware and a manifest of the two, as emu-prepare reads a build: the
# drill boots it and upgrades to the signed candidate.
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

require_workdir
ci="${WRT_WORKDIR}/out/ci"
base="${WRT_WORKDIR}/out/drill-base"
repository=${GITHUB_REPOSITORY:-kiritantakechi/wrt-build}
[ -f "${ci}/manifest.json" ] || die "no build outputs in ${ci}"

rm -rf "${base}"
mkdir -p "${base}/targets"
if tag=$(gh release view --repo "${repository}" --json tagName --jq .tagName 2>/dev/null); then
	gh release download "${tag}" --repo "${repository}" --pattern '*-factory.img.gz' \
		--dir "${base}/targets" || die "cannot download the factory image of ${tag}"
	info "drill base: ${tag}, the latest stable release"
else
	tag=this-build
	cp "${ci}"/targets/*-factory.img.gz "${base}/targets/"
	info "drill base: this build (no stable release yet)"
fi
cp "${ci}/u-boot-qemu.bin" "${base}/"
(cd "${base}" && sha256sum targets/*-factory.img.gz u-boot-qemu.bin) |
	jq -R -n --arg tag "${tag}" \
		'{run: "drill-base", profile: $tag, files: [inputs | split("  ") | {(.[1]): .[0]}] | add}' \
		>"${base}/manifest.json"
