# stale-packages: of a list of apks, one path per line on standard input, those
# of packages the configuration does not build, one path per line
# (scripts/lib/tree.sh: stale_packages). Its arguments: the configuration
# (.config), OpenWrt's package metadata (tmp/.packageinfo), and - for the list.
# A package builds when the configuration selects it (=y or =m); the kernel's
# package always does, and is in neither file (package/kernel/linux/Makefile).
# An apk is named after its package with its ABI version, then -<version>.apk:
# a version starts with a digit and holds no "-" but the one before a release
# (-r<n>), so the name is all before the first such ending.

BEGIN { built["kernel"] = 1 }

function close_package() {
	if (name in selected)
		built[name abi] = 1
	name = ""
}

FILENAME == ARGV[1] {
	if ($0 ~ /^CONFIG_PACKAGE_[^=]+=[ym]$/) {
		package = substr($0, length("CONFIG_PACKAGE_") + 1)
		sub(/=[ym]$/, "", package)
		selected[package] = 1
	}
	next
}

FILENAME == ARGV[2] {
	if (/^Package: /) {
		close_package()
		name = $2
		abi = ""
	} else if (/^ABI-Version: /)
		abi = $2
	next
}

FNR == 1 { close_package() }

{
	apk = $0
	sub(/.*\//, "", apk)
	if (!match(apk, /-[0-9][^-]*(-r[0-9]+)?\.apk$/)) {
		print "cannot tell the package of " $0 > "/dev/stderr"
		failed = 1
		next
	}
	if (!(substr(apk, 1, RSTART - 1) in built))
		print
}

END { exit failed }
