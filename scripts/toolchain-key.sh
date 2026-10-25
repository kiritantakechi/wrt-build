#!/bin/sh
# toolchain-key: print the host-toolchain cache key as key=<value>.
# Usage: scripts/toolchain-key.sh [profile] >>"$GITHUB_OUTPUT"   (default dev)
# The key covers exactly the inputs that change the cached host tools and cross
# toolchain of the profile (design D11): among them the configuration
# toolchain-build.sh builds it from.
set -eu
# shellcheck source=scripts/lib/core.sh
. "$(dirname -- "$0")/lib/core.sh"
use seeds

profile=${1:-dev}

require_linux
tree=$(workdir_tree)
ensure_fhs build "$@"

[ -f "${tree}/feeds.conf" ] || die "no source tree; run 'just fetch' and 'just patch' first"
[ -n "${WRT_BUILD_INPUTS:-}" ] || die "WRT_BUILD_INPUTS is not set; the build environment is too old"

arch=$(uname -m)
# The generic kernel files go with toolchain/: the toolchain's kernel headers come
# from them. Every kernel version's count, a superset of what the toolchain's own
# record covers, so that the key moves whenever that record would (build-integrity D4).
trees=$(git -C "${tree}" rev-parse HEAD:tools HEAD:toolchain HEAD:target/linux/generic)
langs=$(git -C "${tree}/feeds/packages" rev-parse HEAD:lang/golang HEAD:lang/rust)
# The build files that name the stamps of the Go and Rust host builds, which the
# archive carries (build_dir/hostpkg): a prepared stamp hashes the package's
# files and configuration as these define it (build-acceleration D2).
stamps=$(git -C "${tree}" rev-parse HEAD:include/depends.mk HEAD:include/host-build.mk HEAD:rules.mk)
# The board-neutral configuration of the profile, as toolchain-build.sh composes
# it: every seed of the profile and every board's device (board-model D2).
configuration=$(mktemp)
trap 'rm -f "${configuration}"' EXIT INT TERM
compose_seeds "${tree}" "${profile}" "" "${configuration}"
seed=$(sha256sum <"${configuration}")
# The target and subtarget the configuration selects, by their makefiles, which
# name what the toolchain is built for: the architecture, the CPU type, the
# features and the kernel version, whose headers the toolchain carries
# (release-integrity D6). The devices are defined elsewhere (image/).
target=$(sed -n 's/^CONFIG_TARGET_\([a-z0-9]*\)=y$/\1/p' "${configuration}")
subtarget=$(sed -n "s/^CONFIG_TARGET_${target}_\\([a-z0-9]*\\)=y\$/\\1/p" "${configuration}")
definition=$(git -C "${tree}" rev-parse \
	"HEAD:target/linux/${target}/Makefile" "HEAD:target/linux/${target}/${subtarget}/target.mk") ||
	die "the configuration selects no target and subtarget of ${tree}: '${target}' '${subtarget}'"
# Build environment fingerprint (flake.nix: buildInputsId): the store paths of the
# host packages plus the build profile. Test and quality tooling are not part of
# it, so adding them keeps the cached toolchain.
environment=${WRT_BUILD_INPUTS##*/}
# The scripts that build and pack the archive decide what it holds, and so do the
# library modules they load (module-boundaries D8).
set -- "${REPO_DIR}/scripts/toolchain-build.sh" "${REPO_DIR}/scripts/toolchain-pack.sh"
modules=$(loaded_modules "$@")
# shellcheck disable=SC2086 # modules is a newline-separated list of plain paths
recipe=$(cat "$@" ${modules} | sha256sum)

digest=$(printf '%s\n' "${arch}" "${trees}" "${langs}" "${stamps}" "${seed}" "${definition}" "${environment}" "${recipe}" | sha256sum)
printf 'key=toolchain-%s\n' "${digest%% *}"
