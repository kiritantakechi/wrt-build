# image-logs: the source package and the build log directory (under logs/) of
# every package of an image's manifest, from OpenWrt's package metadata
# (tmp/.packageinfo); the two files are its arguments, in that order
# (scripts/lib/warnings.sh: image_logs).

FNR == NR { if ($2 == "-" && $1 != "kernel") wanted[$1] = 1; next }

function found() {
	if ((name abi) in wanted) {
		shipped[name abi] = dir
		if (variant != "") { variants[dir] = variants[dir] " " variant; of[name abi] = variant }
	}
	name = ""
}

/^Source-Makefile: / { found(); dir = $2; sub(/\/Makefile$/, "", dir); next }
/^Package: / { found(); name = $2; abi = ""; variant = ""; next }
/^ABI-Version: / { abi = $2; next }
/^Build-Variant: / { variant = $2; next }

END {
	found()
	for (package in wanted) {
		if (!(package in shipped)) {
			print "no package metadata for " package > "/dev/stderr"
			failed = 1
			continue
		}
		dir = shipped[package]
		source = dir
		sub(/.*\//, "", source)
		n = split(package in of ? of[package] : variants[dir], list)
		if (n == 0) print source "\t" dir | "LC_ALL=C sort -u"
		for (i = 1; i <= n; i++) print source "\t" dir "/" list[i] | "LC_ALL=C sort -u"
	}
	close("LC_ALL=C sort -u")
	exit failed
}
