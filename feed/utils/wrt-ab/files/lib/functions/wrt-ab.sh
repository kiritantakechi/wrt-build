# wrt-ab: the two slots on the boot disk (r4s-ab-rollback design D1, D4). Sourced by
# wrt-slot, wrt-healthcheck and the A/B sysupgrade; POSIX sh, so no locals: every
# function keeps its variables under a wrt_ prefix of its own.

# wrt_ab_slot: print the running slot, a or b, as U-Boot passed it to the kernel.
wrt_ab_slot() {
	read -r wrt_cmdline </proc/cmdline
	for wrt_arg in ${wrt_cmdline}; do
		case "${wrt_arg}" in
			wrt.slot=a | wrt.slot=b)
				echo "${wrt_arg#wrt.slot=}"
				return 0
				;;
			*) ;;
		esac
	done
	return 1
}

# wrt_ab_other <slot>: print the other slot.
wrt_ab_other() {
	case "$1" in
		a) echo b ;;
		*) echo a ;;
	esac
}

# wrt_ab_partitions <slot>: print the slot's boot and root partition numbers.
wrt_ab_partitions() {
	case "$1" in
		a) echo 1 2 ;;
		*) echo 3 4 ;;
	esac
}

# wrt_ab_getenv <name> <default>: print a U-Boot variable, or the default.
wrt_ab_getenv() {
	fw_printenv -n "$1" 2>/dev/null || echo "$2"
}

# wrt_ab_setenv <name> <value> [<name> <value> ...]: write U-Boot variables at once,
# and flush them to the card: a panic or watchdog reset does not wait for writeback.
wrt_ab_setenv() {
	printf '%s %s\n' "$@" | fw_setenv -s - && sync
}
