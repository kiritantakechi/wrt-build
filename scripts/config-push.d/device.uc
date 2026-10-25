// The router's half of config-push (r4s-release-pipeline D6, device-modernization D3),
// sent over SSH for every push, so the router never runs a stale copy.
// Usage: ucode - validate | hashes | apply <service>   (in /tmp/wrt-push)
// config-push uploads each service's new files to /tmp/wrt-push/new/<service>:
//  validate      checks them without touching the configuration: dae's in a
//                scratch directory set up as the dae service would (the entry
//                includes dae.config.config_file, and the other files lie next to
//                it), each uci batch on a copy of /etc/config;
//  hashes        prints the hash of each service as last pushed;
//  apply <name>  saves what the service has now, writes the new files, reloads
//                the service and waits for it to come back; if the reload fails
//                or it does not come back, puts the saved files back, reloads
//                it again and fails.
// What a service's push changes is saved whole, Tailscale's state and the SMB
// users included, and a service is back once its own check passes and every
// daemon that ran before runs on, unrestarted for as long as procd may take to
// act on the change (device-integrity D8). The commands it runs report on
// standard error: standard output is the hashes'.
'use strict';

import { glob, lsdir, mkdir, open, popen, readfile, stat, writefile } from 'fs';
import * as ubus from 'ubus';
import { cursor } from 'uci';

const PUSH = '/tmp/wrt-push';
const NEW = `${PUSH}/new`;
const STATE = '/etc/wrt-config';
const PODS = '/mnt/data/containers/pods';
const SAVED = `${PUSH}/saved`;
const TAILSCALE_KEY = `${STATE}/tailscale.key`;
const TAILSCALE_OPTIONS = `${STATE}/tailscale.options`;
const KSMBD_CONF = '/var/etc/ksmbd/ksmbd.conf';
// Seconds a service has to come back in, and between two of its checks.
const WAIT = 60;
const STEP = 2;

function fail(message) {
	warn(`config-push: ${message}\n`);
	exit(1);
}

// quoted(word): word as one argument of a shell command line.
function quoted(word) {
	return `'${replace(word, "'", "'\\''")}'`;
}

// run(command): run a shell command line, its output on standard error; true when
// it succeeded.
function run(command) {
	return system(`${command} >&2`) == 0;
}

// output(command): what a shell command line prints, its standard error too, and
// whether it succeeded.
function output(command) {
	let process = popen(`${command} 2>&1`);
	let text = process.read('all') ?? '';

	return { text: trim(text), ok: process.close() == 0 };
}

function basename(path) {
	return match(path, /[^\/]+$/)[0];
}

function validate() {
	if (stat(`${NEW}/dae`)) {
		let check = `${PUSH}/dae-check`;
		let entry = basename(cursor().get('dae', 'config', 'config_file') ?? '/etc/dae/config.dae');

		if (!stat(`${NEW}/dae/${entry}`))
			fail(`dae: ${entry} is not among the files`);

		if (!run(`rm -rf ${quoted(check)} && mkdir -p ${quoted(check)} && cp ${quoted(`${NEW}/dae`)}/* ${quoted(check)}/`))
			fail('dae: cannot set up the files to validate');

		writefile(`${check}/main.dae`,
			"global {\n\tlan_interface: br-lan\n}\n" +
			"dns {\n\tbind: '127.0.0.1:5353'\n}\n" +
			`include {\n\t${entry}\n}\n`);

		if (!run(`chmod 600 ${quoted(check)}/* && dae validate -c ${quoted(`${check}/main.dae`)}`))
			fail('dae does not accept the configuration');
	}

	for (let batch in sort(glob(`${NEW}/*/*.uci`) ?? [])) {
		let copy = `${PUSH}/uci-check`;

		if (!run(`rm -rf ${quoted(copy)} && cp -a /etc/config ${quoted(copy)}`))
			fail('cannot copy /etc/config to check the batches on');

		let result = output(`uci -c ${quoted(copy)} batch < ${quoted(batch)}`);

		if (!result.ok || length(result.text))
			fail(`${basename(batch)}: ${length(result.text) ? result.text : 'failed'}`);
	}
}

// services(): the services config-push uploaded files of.
function services() {
	return sort(filter(lsdir(NEW) ?? [], (name) => stat(`${NEW}/${name}`)?.type == 'directory'));
}

function hashes() {
	mkdir(STATE);

	for (let name in services())
		printf('%s %s\n', name, trim(readfile(`${STATE}/${name}`) ?? '') || 'none');
}

// has_entry(file, name): the passwd-style file has an entry for name.
function has_entry(file, name) {
	return length(filter(split(readfile(file) ?? '', '\n'), (line) => index(line, `${name}:`) == 0)) > 0;
}

// append(file, line): add a line to the end of the file.
function append(file, line) {
	let handle = open(file, 'a') ?? fail(`cannot write ${file}`);

	handle.write(`${line}\n`);
	handle.close();
}

// tailscale_state(): where tailscaled keeps its node's state, its login among it.
function tailscale_state() {
	return cursor().get('tailscale', 'settings', 'state_file') ?? '/etc/tailscale/tailscaled.state';
}

// owned(name): the paths a push of the service changes, files or directories.
function owned(name) {
	switch (name) {
	case 'dae':
		return ['/etc/dae', '/etc/config/dae'];

	case 'pods':
		return [PODS];

	case 'smb':
		return ['/etc/passwd', '/etc/group', '/etc/ksmbd/ksmbdpwd.db'];

	case 'tailscale':
		return [TAILSCALE_KEY, TAILSCALE_OPTIONS, `${STATE}/tailscale.login`, tailscale_state()];

	default:
		return ['/etc/config'];
	}
}

// The paths a service's push changes: save them, absent ones as absent, and put
// them back as they were, removing what the push added.
function save(name) {
	let saved = `${SAVED}/${name}`;

	if (!run(`rm -rf ${quoted(saved)} && mkdir -p ${quoted(saved)}`))
		fail(`${name}: cannot save its files`);

	for (let i, path in owned(name))
		if (stat(path) && !run(`cp -a ${quoted(path)} ${quoted(`${saved}/${i}`)}`))
			fail(`${name}: cannot save ${path}`);
}

// put_back(copy, path): the path as its saved copy has it, or gone when it had
// none. A file is replaced in one rename; a directory gets the copy over it, then
// loses what the push added: neither is ever missing meanwhile.
function put_back(copy, path) {
	switch (stat(copy)?.type) {
	case null:
		return run(`rm -rf ${quoted(path)}`);

	case 'directory':
		return run(`mkdir -p ${quoted(path)} && cp -a ${quoted(copy)}/. ${quoted(path)}/` +
			` && cd ${quoted(path)} && for entry in * .[!.]*; do` +
			' { [ -e "${entry}" ] || [ -L "${entry}" ]; } || continue;' +
			` [ -e ${quoted(copy)}/"\${entry}" ] || [ -L ${quoted(copy)}/"\${entry}" ] || rm -rf "\${entry}"; done`);

	default:
		return run(`cp -a ${quoted(copy)} ${quoted(`${path}.restored`)}` +
			` && mv ${quoted(`${path}.restored`)} ${quoted(path)}`);
	}
}

function restore(name) {
	let saved = `${SAVED}/${name}`;

	for (let i, path in owned(name))
		if (!put_back(`${saved}/${i}`, path))
			warn(`config-push: ${name}: cannot put ${path} back\n`);
}

function write(name) {
	let files = `${NEW}/${name}`;

	switch (name) {
	case 'dae':
		for (let file in glob(`${files}/*`) ?? []) {
			let target = `/etc/dae/${basename(file)}`;

			if (!run(`cp ${quoted(file)} ${quoted(target)} && chmod 600 ${quoted(target)}`))
				fail(`dae: cannot write ${target}`);
		}

		let uci = cursor();

		uci.set('dae', 'config', 'enabled', '1');
		uci.commit('dae');
		break;

	case 'pods':
		if (!run(`mkdir -p '${PODS}' && cp ${quoted(files)}/* '${PODS}/'`))
			fail('pods: cannot write the Pods');
		break;

	case 'smb':
		// A user per line, its password after the first blank.
		for (let line in split(readfile(`${files}/users`) ?? '', '\n')) {
			let entry = match(trim(line), /^(\S+)\s+(.*)$/);

			if (!entry)
				continue;

			let user = entry[1], password = entry[2];

			if (!has_entry('/etc/passwd', user))
				append('/etc/passwd', `${user}:x:1000:1000::/var:/bin/false`);

			if (!has_entry('/etc/group', user))
				append('/etc/group', `${user}:x:1000:`);

			if (!run(`ksmbd.adduser -p ${quoted(password)} ${quoted(user)}`))
				fail(`smb: cannot add ${user}`);
		}
		break;

	case 'tailscale':
		// The key readable by root alone; the login of an older push goes.
		if (!run(`mkdir -p ${STATE} && cp ${quoted(`${files}/auth_key`)} ${TAILSCALE_KEY}` +
			` && chmod 600 ${TAILSCALE_KEY} && cp ${quoted(`${files}/options`)} ${TAILSCALE_OPTIONS}` +
			` && rm -f ${STATE}/tailscale.login`))
			fail('tailscale: cannot write its login');
		break;

	default:
		for (let batch in sort(glob(`${files}/*.uci`) ?? []))
			if (!run(`uci batch < ${quoted(batch)}`))
				fail(`${basename(batch)}: uci batch failed`);

		run('uci commit');
	}
}

// reload(name): have the service take its configuration; false when the command
// that does so fails. Whether the service came back is for settle to tell.
function reload(name) {
	switch (name) {
	case 'dae':
		return run('/etc/init.d/dae restart');

	case 'pods':
		return !stat(PODS) || run('/etc/init.d/wrt-containers restart');

	case 'smb':
		return run('/etc/init.d/ksmbd restart');

	case 'tailscale':
		// The key from its file, never on the command line; the options are
		// separate words. tailscale up takes a key only to log in anew, which a
		// node logged in already does with --force-reauth alone. A key control
		// refuses fails it, while tailscaled keeps its earlier login and reports
		// itself running.
		return run(`tailscale up --reset --force-reauth --auth-key=file:${TAILSCALE_KEY}` +
			` ${trim(readfile(TAILSCALE_OPTIONS) ?? '')} --timeout=60s`);

	case 'network':
		return run('/etc/init.d/network reload');

	default:
		return run('reload_config');
	}
}

// restart_restored(name): have the service take back its saved files, as reload
// does. Tailscale starts again on its saved state rather than logging in once
// more: the key of an earlier login may be spent.
function restart_restored(name) {
	return name == 'tailscale' ? run('/etc/init.d/tailscale restart') : reload(name);
}

// procd_services(verbose): procd's services, with their triggers if verbose.
function procd_services(verbose) {
	let connection = ubus.connect();
	let services = connection?.call('service', 'list', { verbose }) ?? {};

	connection?.disconnect();

	return services;
}

// daemons(): the procd instances that run and are respawned when they end, the
// services' daemons: service/instance to its incarnation, which procd counts up
// whenever it starts an instance.
function daemons() {
	let found = {};

	for (let service, description in procd_services(false))
		for (let instance, state in description.instances ?? {})
			if (state.running && (state.respawn ?? state.respawn_policy))
				found[`${service}/${instance}`] = state.incarnation;

	return found;
}

// quiet(before): the seconds procd may take to act on a change and have the
// daemons (before) show it: its longest trigger delay; the longest one of them
// takes to stop before it starts again, at most twice its term_timeout (a jailed
// instance's); and a check's time for the init scripts procd runs.
function quiet(before) {
	let delay = 0, stop = 0;

	for (let service, description in procd_services(true)) {
		for (let trigger in description.triggers ?? [])
			delay = max(delay, (trigger[2] ?? 0) / 1000);

		for (let instance, state in description.instances ?? {})
			if (`${service}/${instance}` in before)
				stop = max(stop, 2 * (state.term_timeout ?? 0));
	}

	return delay + stop + STEP;
}

// pods_running(): every declared Pod runs.
function pods_running() {
	for (let declaration in glob(`${PODS}/*.yaml`) ?? []) {
		let pod = replace(basename(declaration), /\.yaml$/, '');

		if (output(`podman pod inspect --format '{{.State}}' ${quoted(pod)}`).text != 'Running')
			return false;
	}

	return true;
}

// sharing(): ksmbd runs if its configuration offers a share.
function sharing() {
	let offered = filter(split(readfile(KSMBD_CONF) ?? '', '\n'),
		(line) => match(line, /^\[/) && line != '[global]');

	return !length(offered) || system('pidof ksmbd.mountd >/dev/null') == 0;
}

// back(name, before, running): the service is back after its reload: its own
// check passes, and every daemon that ran before (before) runs (running).
function back(name, before, running) {
	let ok;

	switch (name) {
	case 'dae':
		ok = system('/etc/healthcheck.d/50-dae >/dev/null 2>&1') == 0;
		break;

	case 'network':
		let connection = ubus.connect();
		let lan = connection?.call('network.interface.lan', 'status');

		connection?.disconnect();
		ok = lan?.up == true;
		break;

	case 'pods':
		ok = pods_running();
		break;

	case 'smb':
		ok = sharing();
		break;

	case 'tailscale':
		ok = system('tailscale status >/dev/null 2>&1') == 0;
		break;

	default:
		ok = true;
	}

	return ok && length(filter(keys(before), (daemon) => !(daemon in running))) == 0;
}

// settle(name, before): wait until the service is back, and every daemon that
// ran before runs through one incarnation for quiet() seconds. procd acts on a
// change after a delay, and respawns a daemon that fails, which then runs for a
// moment at a time: a reload still to come, a restart under way and a failing
// daemon all break the run. True if the service came back within WAIT.
function settle(name, before) {
	let needed = quiet(before);
	let steady = 0, last = null;

	for (let waited = 0; waited <= WAIT + needed; waited += STEP) {
		let now = daemons();
		let same = last && length(filter(keys(before), (daemon) => now[daemon] != last[daemon])) == 0;

		steady = back(name, before, now) && same ? steady + STEP : 0;
		last = now;

		if (steady >= needed)
			return true;

		sleep(STEP * 1000);
	}

	return false;
}

function apply(name) {
	let before = daemons();

	save(name);
	write(name);

	if (reload(name) && settle(name, before)) {
		mkdir(STATE);
		writefile(`${STATE}/${name}`, readfile(`${NEW}/${name}.sha256`) ?? '');

		return;
	}

	restore(name);

	if (!restart_restored(name) || !settle(name, before))
		fail(`${name} did not come back with the new configuration, nor with the previous one`);

	fail(`${name} did not come back with the new configuration; the previous one is back`);
}

switch (ARGV[0]) {
case 'validate':
	validate();
	break;

case 'hashes':
	hashes();
	break;

case 'apply':
	apply(ARGV[1]);
	break;

default:
	fail('usage: validate | hashes | apply <service>');
}
