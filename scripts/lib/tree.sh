# tree: the build tree's files: what lives outside it, linked in; files written
# only when their content changes; its configuration; and its checkout.
# Usage: use tree   (POSIX sh; sourced)
# shellcheck shell=sh
: "${REPO_DIR:?load scripts/lib/core.sh first}"

# symlink <target> <link>: make <link> point to <target>, leaving a link that
# already does as it is. The kernel's configuration follows its inputs'
# times, a link's own among them (build-acceleration D4).
symlink() (
	current=$(readlink "$2") || current=
	[ "${current}" = "$1" ] || ln -sfn "$1" "$2"
)

# update_file <file>: write standard input to <file>, leaving a file that holds
# it already as it is, modification time included (build-acceleration D4).
update_file() (
	cat >"$1.new"
	if cmp -s "$1.new" "$1"; then
		rm -f "$1.new"
	else
		mv -f "$1.new" "$1"
	fi
)

# link_tree <tree>: put what lives outside the tree where the build reads it
# (design D7): the rootfs overlay, the kernel configuration overlay and the
# compiler cache (files/, env/ and .ccache are all gitignored upstream). The
# cache reads its settings from config/ccache.conf.
link_tree() (
	[ -d "$1" ] || die "link_tree: no build tree at $1"
	workdir=${1%/*}
	symlink "${REPO_DIR}/files" "$1/files"
	mkdir -p "$1/env" "$1/tmp" "${workdir}/out"
	symlink "${REPO_DIR}/config/kernel.config" "$1/env/kernel-config"
	# The compiler caches live beside the tree, one per language, linked where
	# rules.mk, the feed's Go values and its Rust values look for them
	# (build-acceleration D6).
	cache="${workdir}/compiler-cache"
	[ -L "$1/tmp/go-build" ] || [ ! -e "$1/tmp/go-build" ] ||
		die "$1/tmp/go-build is a directory; move it to ${cache}/go-build"
	mkdir -p "${cache}/ccache" "${cache}/go-build" "${cache}/sccache"
	symlink "${cache}/ccache" "$1/.ccache"
	symlink "${cache}/go-build" "$1/tmp/go-build"
	symlink "${cache}/sccache" "$1/.sccache"
	symlink "${REPO_DIR}/config/ccache.conf" "${cache}/ccache/ccache.conf"
)

# kernel_dir <build dir>: the kernel build directory in a board's build directory
# (make val.BUILD_DIR); exactly one must exist.
kernel_dir() (
	set -- "$1"/linux-rockchip_armv8/linux-[0-9]*
	[ "$#" -eq 1 ] && [ -d "$1" ] ||
		die "expected one kernel build directory, found: $* (clean the old one)"
	printf '%s\n' "$1"
)

# missing_config_lines <wanted> <actual>: print each option line of <wanted>
# (CONFIG_X=... or "# CONFIG_X is not set") that <actual> lacks verbatim. Symbols
# may hold any character but "=" and blanks: packages' hold "-", "." and "+".
missing_config_lines() (
	grep -E '^(CONFIG_[^=[:space:]]+=|# CONFIG_[^[:space:]]+ is not set$)' "$1" |
		while IFS= read -r line; do
			grep -Fxq -- "${line}" "$2" || printf '  %s\n' "${line}"
		done
)

# configure_tree <tree> <seed file>: the tree's .config from the seeds. Fails if
# make defconfig dropped or changed any of their lines (renamed or removed
# options, unmet dependencies). A configuration the same as the one its build
# directories were last configured with keeps that one's time
# (tmp/wrt-config-<build>, the build being host or the build directories'
# suffix): the kernel's configuration follows .config's time, and every kernel
# module follows the kernel's (build-acceleration D4).
configure_tree() (
	[ -d "$1" ] || die "configure_tree: no build tree at $1"
	cp "$2" "$1/.config"
	make -C "$1" defconfig >/dev/null
	missing=$(missing_config_lines "$2" "$1/.config")
	if [ -n "${missing}" ]; then
		printf 'error: defconfig dropped or changed these seed lines:\n%s\n' "${missing}" >&2
		exit 1
	fi
	suffix=$(sed -n 's/^CONFIG_BUILD_SUFFIX="\(.*\)"$/\1/p' "$1/.config")
	last="$1/tmp/wrt-config-${suffix:-host}"
	if cmp -s "$1/.config" "${last}"; then
		touch -r "${last}" "$1/.config"
	else
		cp -p "$1/.config" "${last}"
	fi
)

# move_tree <repository> <commit>: put the work tree on <commit>, detached. git
# writes only the files whose content differs from the commit the tree was on,
# so every other file keeps its modification time, and make rebuilds only what
# changed (build-acceleration D5). A file whose time changed but not its content
# counts as unchanged too: the index is refreshed first, or checkout would take
# it for a local change and write it again. Untracked files that are not ignored
# go, such as a patch a package would apply, but version.date, which patch.sh
# keeps; ignored build output stays.
move_tree() (
	git -C "$1" update-index -q --refresh >/dev/null || true
	git -C "$1" -c advice.detachedHead=false checkout -q -f --detach "$2"
	git -C "$1" clean -q -f -d -e /version.date
	head=$(git -C "$1" rev-parse HEAD)
	wanted=$(git -C "$1" rev-parse "$2^{commit}")
	[ "${head}" = "${wanted}" ] || die "$1 is not at $2"
)
