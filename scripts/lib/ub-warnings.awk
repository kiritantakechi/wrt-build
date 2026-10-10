# ub-warnings: the UB-indicative warnings of a build log, one per line: option,
# file, function and line, tab-separated (scripts/lib/warnings.sh: ub_warnings).
# The options are the words of ENVIRON["UB_WARNINGS"], without their -W. Run it
# in the C locale: GCC quotes in UTF-8 in a UTF-8 locale.

function strip(path) {
	if (sub(/^.*\/build_dir\/[^\/]+\/[^\/]+\//, "", path))
		sub(/^[^\/]*-[0-9][^\/]*\//, "", path)
	sub(/^.*\/staging_dir\/[^\/]+\//, "", path)
	while (sub(/^\.\.?\//, "", path)) {}
	while (sub(/\/\.\//, "/", path)) {}
	return path
}

# The function of the source: GCC names its clones after it, with suffixes such
# as .isra, .part.0 or .constprop.0 that follow the optimization.
function source(name) {
	if (name ~ /^[A-Za-z_][A-Za-z0-9_]*\./) sub(/\..*$/, "", name)
	return name
}

function quoted(text) {
	text = substr(text, index(text, "'") + 1)
	return substr(text, 1, index(text, "'") - 1)
}

BEGIN {
	n = split(ENVIRON["UB_WARNINGS"], list)
	for (i = 1; i <= n; i++) ub[list[i]] = 1
}

{ gsub(/\342\200\230|\342\200\231/, "'") }

# A chain of inlined calls leads straight to its diagnostic. Any other line after
# it comes from another job that wrote to the log at the same time, and the chain
# belongs to no diagnostic after it.
$0 !~ /^([^ :]+: )?In [^']*'.*',$|^ +inlined from |^[^ :]+:[0-9]+(:[0-9]+)?: (warning|error|note): / {
	inlined = ""
	at = ""
}

/^[^ :]+: (In|At) .*:$/ {
	context = substr($0, 1, index($0, ": ") - 1)
	if (index($0, "'")) function_ = quoted($0)
	else if ($0 ~ /: At /) function_ = ""
	else { function_ = substr($0, index($0, ": In ") + 5); sub(/:$/, "", function_) }
	next
}

/^([^ :]+: )?In [^']*'.*',$/ { inlined = quoted($0); at = ""; next }

/^ +inlined from '.*' at [^ ]+[,:]$/ && inlined != "" {
	inlined = quoted($0)
	at = substr($0, index($0, "' at ") + 5)
	next
}

# Every diagnostic, a note as well, consumes the context lines before it.
/^[^ :]+:[0-9]+(:[0-9]+)?: (warning|error|note): / {
	chain = inlined; call = at; inlined = ""; at = ""
	if ($0 !~ /: warning: / || !match($0, /\[-W[a-z0-9-]+=?\]$/)) next
	option = substr($0, RSTART + 3, RLENGTH - 4)
	sub(/=$/, "", option)
	if (!(option in ub)) next
	split(call != "" ? call : $0, location, ":")
	if (chain != "") { context = location[1]; function_ = chain }
	print "-W" option "\t" strip(location[1]) "\t" \
		(location[1] == context ? source(function_) : "") "\t" location[2] | "LC_ALL=C sort -u"
}

END { close("LC_ALL=C sort -u") }
