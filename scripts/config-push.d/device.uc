// The router's half of config-push (r4s-release-pipeline D6, device-modernization D3),
// sent over SSH for every push, so the router never runs a stale copy.
// Usage: ucode - validate | hashes | apply <service>   (in /tmp/wrt-push)
// config-push uploads each service's new files to /tmp/wrt-push/new/<service>:
//  validate      checks them without touching the configuration: honk's with
//                honk's own check of the entry its service would write around
//                honk.config.config_file (/etc/init.d/honk check), each uci batch
//                on a copy of /etc/config;
//  hashes        prints the hash of each service as last pushed;
//  apply <name>  saves what the service has now, writes the new files, reloads
//                the service and waits for it to come back; if the reload fails
//                or it does not come back, puts the saved files back, reloads
//                it again and fails.
// What a service's push changes is saved whole, Tailscale's state and the SMB
// users included, and a service is back once procd has run what the change
// queued, its own check passes and every daemon that ran before runs on,
// unrestarted for as long as a restart may take (device-integrity D8). The
// commands it runs report on standard error: standard output is the hashes'.
'use strict';

import { glob, lsdir, lstat, mkdir, open, popen, readfile, stat } from 'fs';
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
// Seconds procd has to run what a change queued, a service then has to come
// back in, and between two of its checks.
const QUEUE_WAIT = 300;
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
	if (stat(`${NEW}/honk`)) {
		let entry = basename(cursor().get('honk', 'config', 'config_file') ?? '/etc/honk/config.dae');

		if (!stat(`${NEW}/honk/${entry}`))
			fail(`honk: ${entry} is not among the files`);

		if (!run(`/etc/init.d/honk check ${quoted(`${NEW}/honk/${entry}`)}`))
			fail('honk does not accept the configuration');
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
	case 'honk':
		// Its start-at-boot switch is the init script's rc.d links.
		return ['/etc/honk', '/etc/config/honk', '/etc/rc.d/S99honk', '/etc/rc.d/K01honk'];

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
		if (lstat(path) && !run(`cp -a ${quoted(path)} ${quoted(`${saved}/${i}`)}`))
			fail(`${name}: cannot save ${path}`);
}

// put_back(copy, path): the path as its saved copy has it, or gone when it had
// none. A file or a symbolic link is replaced in one rename; a directory gets the
// copy over it, then loses what the push added: neither is ever missing
// meanwhile. A saved link is a link, whatever its target, which a relative one
// misses from where it is saved.
function put_back(copy, path) {
	switch (lstat(copy)?.type) {
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
	case 'honk':
		// The pushed files replace the directory's, readable by root alone, and
		// honk starts at boot from now on.
		if (!run(`rm -rf /etc/honk.new && mkdir -m 700 /etc/honk.new && cp ${quoted(files)}/* /etc/honk.new/` +
			' && chmod 600 /etc/honk.new/* && rm -rf /etc/honk && mv /etc/honk.new /etc/honk' +
			' && /etc/init.d/honk enable'))
			fail('honk: cannot write its configuration');
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
	case 'honk':
		return run('/etc/init.d/honk restart');

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

// procd_services(): procd's services.
function procd_services() {
	let connection = ubus.connect();
	let services = connection?.call('service', 'list') ?? {};

	connection?.disconnect();

	return services;
}

// trigger_commands(): the commands procd's triggers queued that have yet to
// end. procd runs them one at a time, each after its trigger's delay, so a
// change's own can wait behind those of every other change.
function trigger_commands() {
	let connection = ubus.connect();
	let reply = connection?.call('service', 'trigger_commands');

	connection?.disconnect();

	return reply?.commands ?? fail('procd does not report its trigger commands');
}

// daemons(): the procd instances that run and are respawned when they end, the
// services' daemons: service/instance to its incarnation, which procd counts up
// whenever it starts an instance.
function daemons() {
	let found = {};

	for (let service, description in procd_services())
		for (let instance, state in description.instances ?? {})
			if (state.running && (state.respawn ?? state.respawn_policy))
				found[`${service}/${instance}`] = state.incarnation;

	return found;
}

// quiet(before): the seconds the daemons (before) may take to show a change
// procd has acted on: the longest one of them takes to stop before it starts
// again, at most twice its term_timeout (a jailed instance's), and a check's time.
function quiet(before) {
	let stop = 0;

	for (let service, description in procd_services())
		for (let instance, state in description.instances ?? {})
			if (`${service}/${instance}` in before)
				stop = max(stop, 2 * (state.term_timeout ?? 0));

	return stop + STEP;
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

// back(name): the service's own check passes after its reload.
function back(name) {
	switch (name) {
	case 'honk':
		return system('/etc/healthcheck.d/50-honk >/dev/null 2>&1') == 0;

	case 'network':
		let connection = ubus.connect();
		let lan = connection?.call('network.interface.lan', 'status');

		connection?.disconnect();

		return lan?.up == true;

	case 'pods':
		return pods_running();

	case 'smb':
		return sharing();

	case 'tailscale':
		return system('tailscale status >/dev/null 2>&1') == 0;

	default:
		return true;
	}
}

// acted(): wait until procd has run every command its triggers queued; true if
// it did within QUEUE_WAIT. A command that hangs would hold up all the others.
function acted() {
	let commands;

	for (let waited = 0; waited <= QUEUE_WAIT; waited += STEP) {
		commands = trigger_commands();

		if (!length(commands))
			return true;

		sleep(STEP * 1000);
	}

	warn(`config-push: procd still has to run: ${join(' ', commands[0].command)}\n`);

	return false;
}

// settle(name, before): wait until procd has acted on the change, then until the
// service's own check passes, and every daemon that ran before runs through one
// incarnation for quiet() seconds. A restart under way and a failing daemon, which
// procd respawns and which then runs for a moment at a time, break the run; the
// commands other services' triggers bring all the while, on interface events for
// one, do not. True if the service came back within WAIT of procd's acting on the
// change; otherwise says what kept it from counting as back.
function settle(name, before) {
	if (!acted())
		return false;

	let needed = quiet(before);
	let steady = 0, last = null, holding;

	for (let waited = 0; waited <= WAIT + needed; waited += STEP) {
		let now = daemons();
		let stopped = filter(keys(before), (daemon) => !(daemon in now));
		let restarted = filter(keys(before), (daemon) => last && daemon in now && now[daemon] != last[daemon]);

		holding = [];

		if (!back(name))
			push(holding, 'its own check fails');

		if (length(stopped))
			push(holding, `stopped: ${join(' ', stopped)}`);

		if (length(restarted))
			push(holding, `restarted: ${join(' ', restarted)}`);

		steady = last && !length(holding) ? steady + STEP : 0;
		last = now;

		if (steady >= needed)
			return true;

		sleep(STEP * 1000);
	}

	warn(`config-push: ${name}: ${join('; ', holding)}\n`);

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
