// wrt.ab: the two slots on the boot disk (r4s-ab-rollback D1, D4): the running
// slot, the other one, and the U-Boot variables that pick and confirm a slot.
// The sysupgrade hook keeps these facts in shell (/lib/functions/wrt-ab.sh),
// as its second stage runs from a RAM root without ucode.
'use strict';

import { popen, readfile } from 'fs';

// slot(): the running slot, "a" or "b", as U-Boot passed it to the kernel; null
// on a system not booted from a slot.
export function slot() {
	let found = match(readfile('/proc/cmdline') ?? '', /(^|\s)wrt\.slot=(a|b)(\s|$)/);

	return found ? found[2] : null;
}

// environment(cmdline): the copies of the U-Boot environment that the bootloader
// named on the kernel command line (wrt.env=<size>@<offset>,...), as { size,
// offset } in its hexadecimal notation: the only places the system may read and
// write it (trial-boot-resilience D2, D3). null when it named none, as a
// bootloader from before two copies does. cmdline defaults to this boot's.
export function environment(cmdline) {
	let found = match(cmdline ?? readfile('/proc/cmdline') ?? '', /(^| )wrt\.env=([^ \n]+)/);
	let copies = [];

	for (let copy in split(found?.[2] ?? '', ',')) {
		let place = match(copy, /^(0x[0-9A-Fa-f]+)@(0x[0-9A-Fa-f]+)$/);

		if (!place)
			return null;

		push(copies, { size: place[1], offset: place[2] });
	}

	return length(copies) ? copies : null;
}

// other(running): the slot that is not running.
export function other(running) {
	return running == 'a' ? 'b' : 'a';
}

// getenv(name, fallback): a U-Boot variable, or fallback when it is not set.
export function getenv(name, fallback) {
	let tool = popen(`fw_printenv -n ${name} 2>/dev/null`);
	let value = trim(tool.read('all') ?? '');

	return tool.close() == 0 ? value : fallback;
}

// setenv(variables): write U-Boot variables at once, then flush them to the disk:
// a panic or watchdog reset does not wait for writeback. True when both worked.
export function setenv(variables) {
	let tool = popen('fw_setenv -s - && sync', 'w');

	for (let name in variables)
		tool.write(`${name} ${variables[name]}\n`);

	return tool.close() == 0;
}
