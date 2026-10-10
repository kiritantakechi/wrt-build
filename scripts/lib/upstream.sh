# upstream: the upstream sources pinned in upstream.lock, fetched and put on
# their pinned commits with the repository's patches applied.
# Usage: use upstream   (POSIX sh; sourced)
# shellcheck shell=sh
: "${REPO_DIR:?load scripts/lib/core.sh first}"
use tree

LOCK_FILE="${REPO_DIR}/upstream.lock"

# lock_field <name> <field>: field is url, sha or epoch.
lock_field() (
	awk -v name="$1" -v field="$2" '
		/^[[:space:]]*(#|$)/ { next }
		$1 == name {
			if (field == "url") print $2
			else if (field == "sha") print $3
			else if (field == "epoch") print $4
			found = 1
		}
		END { if (!found) exit 1 }
	' "${LOCK_FILE}" || die "upstream.lock has no entry for '$1'"
)

# lock_sha256: the hash of upstream.lock, which names every upstream source.
lock_sha256() (
	sum=$(sha256sum "${LOCK_FILE}")
	echo "${sum%% *}"
)

# lock_feeds: feed names in lock order (everything except openwrt itself).
lock_feeds() (
	awk '/^[[:space:]]*(#|$)/ { next } $1 != "openwrt" { print $1 }' "${LOCK_FILE}"
)

# fetch_locked <name> <dir>: make the pinned commit of <name> available in <dir>,
# shallow-fetched once, and check it out when <dir> is a new tree. An existing
# tree stays where it is, for patch_tree to move (build-acceleration D5).
fetch_locked() (
	dir=$2
	url=$(lock_field "$1" url)
	sha=$(lock_field "$1" sha)
	if [ ! -d "${dir}/.git" ]; then
		mkdir -p "${dir}"
		git -C "${dir}" init -q
		git -C "${dir}" remote add origin "${url}"
	fi
	git -C "${dir}" remote set-url origin "${url}"
	if ! git -C "${dir}" cat-file -e "${sha}^{commit}" 2>/dev/null; then
		git -C "${dir}" fetch -q --depth 1 origin "${sha}"
	fi
	git -C "${dir}" rev-parse -q --verify HEAD >/dev/null || move_tree "${dir}" "${sha}"
)

# series_commit <patch dir> <repository> <base>: print the commit of <base> with
# <patch dir>/*.patch applied in name order. It is made in the object database,
# on an index of its own, so the work tree stays as it is: what git am makes of
# the series, with each patch's author, its date for both dates, and a fixed
# committer, so the same series always gives the same commit. Dies naming the
# first patch that does not apply.
series_commit() (
	dir=$1 repository=$2 commit=$3
	scratch=$(mktemp -d "${TMPDIR:-/tmp}/wrt-series.XXXXXX")
	trap 'rm -rf "${scratch}"' EXIT
	export GIT_INDEX_FILE="${scratch}/index" \
		GIT_COMMITTER_NAME=wrt-build GIT_COMMITTER_EMAIL=wrt-build@localhost
	git -C "${repository}" read-tree "${commit}"
	for patch in "${dir}"/*.patch; do
		[ -e "${patch}" ] || continue
		name=${patch#"${REPO_DIR}/"}
		git -C "${repository}" mailinfo "${scratch}/message" "${scratch}/diff" \
			<"${patch}" >"${scratch}/info" || die "not a patch: ${name}"
		if ! git -C "${repository}" apply --cached "${scratch}/diff"; then
			die "patch does not apply: ${name}"
		fi
		tree=$(git -C "${repository}" write-tree)
		author=$(sed -n 's/^Author: //p' "${scratch}/info")
		email=$(sed -n 's/^Email: //p' "${scratch}/info")
		date=$(sed -n 's/^Date: //p' "${scratch}/info")
		subject=$(sed -n 's/^Subject: //p' "${scratch}/info")
		commit=$(
			{
				printf '%s\n\n' "${subject}"
				cat "${scratch}/message"
			} | git stripspace |
				GIT_AUTHOR_NAME=${author} GIT_AUTHOR_EMAIL=${email} \
					GIT_AUTHOR_DATE=${date} GIT_COMMITTER_DATE=${date} \
					git -C "${repository}" commit-tree "${tree}" -p "${commit}"
		)
		info "applied ${name}"
	done
	printf '%s\n' "${commit}"
)

# patch_tree <name> <dir>: put <dir> on the pinned commit of <name> with
# patches/<name>/*.patch applied (series_commit, then move_tree).
patch_tree() (
	sha=$(lock_field "$1" sha)
	commit=$(series_commit "${REPO_DIR}/patches/$1" "$2" "${sha}")
	move_tree "$2" "${commit}"
)
