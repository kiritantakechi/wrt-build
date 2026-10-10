# toolchain: what a toolchain was built with: its C library and Rust's standard
# libraries, and the stages of a build that built any of it.
# Usage: use toolchain   (POSIX sh; sourced)
# shellcheck shell=sh
: "${REPO_DIR:?load scripts/lib/core.sh first}"

# toolchain_libc <toolchain dir>: the hash of the toolchain's C library, or
# nothing when it has none (board-model D2: the record in wrt-toolchain.json
# names it).
toolchain_libc() (
	[ -f "$1/lib/libc.so" ] || return 0
	sum=$(sha256sum "$1/lib/libc.so")
	echo "${sum%% *}"
)

# toolchain_rust_std <tree>: the hash of the Rust standard libraries in the
# tree's staging_dir/hostpkg, the target's among them, or nothing when Rust is
# not built (build-acceleration D7): a rebuild changes it, as it does libc.so.
# Rust's uninstaller leaves its directories, so it is the libraries that count.
toolchain_rust_std() (
	[ -d "$1" ] || die "toolchain_rust_std: no build tree at $1"
	rustlib="$1/staging_dir/hostpkg/lib/rustlib"
	[ -d "${rustlib}" ] || return 0
	cd "${rustlib}" || return
	rlibs=$(find . -path './*/lib/*.rlib' -type f | LC_ALL=C sort)
	[ -n "${rlibs}" ] || return 0
	sum=$(printf '%s\n' "${rlibs}" | xargs sha256sum | sha256sum)
	echo "${sum%% *}"
)

# toolchain_stages <time log>: the stages of a build's time log that built part of
# the toolchain (tools, the cross toolchain, Go or Rust), which only toolchain-build
# builds (build-acceleration D7), one per line.
toolchain_stages() (
	awk -F '\t' '$2 == "begin" && ($4 ~ /^(tools|toolchain)\// ||
		$4 ~ /^package\/feeds\/packages\/(golang|golang-bootstrap|golang1\.[0-9]+|rust)$/) {
		print $4 " [" $3 "]"
	}' "$1" | LC_ALL=C sort -u
)
