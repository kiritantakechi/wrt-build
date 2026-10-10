# merge-seeds: the lines of the seed files in order, each option only in the last
# line that sets it (CONFIG_X=..., or "# CONFIG_X is not set"), where that line
# stands. Comments and blank lines stay (scripts/lib/seeds.sh: merge_seeds).

function option(text) {
	if (text ~ /^CONFIG_[^= ]+=/) { sub(/=.*/, "", text); return text }
	if (text ~ /^# CONFIG_[^ ]+ is not set$/) { split(text, word, " "); return word[2] }
	return ""
}

{ line[NR] = $0; name = option($0); if (name != "") last[name] = NR }

END {
	for (i = 1; i <= NR; i++) {
		name = option(line[i])
		if (name == "" || last[name] == i) print line[i]
	}
}
