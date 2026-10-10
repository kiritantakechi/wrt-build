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
//                the service and waits for it to come back; if it does not, puts
//                the saved files back, reloads it again and fails.
// The commands it runs report on standard error: standard output is the hashes'.
'use strict';

import { glob, lsdir, mkdir, open, popen, readfile, stat, writefile } from 'fs';
import * as ubus from 'ubus';
import { cursor } from 'uci';

const PUSH = '/tmp/wrt-push';
const NEW = `${PUSH}/new`;
const STATE = '/etc/wrt-config';
const PODS = '/mnt/data/containers/pods';
const WAIT = 60;

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

// The files of a service on the router: save, restore and write them.
function save(name) {
	let saved = quoted(`${PUSH}/saved/${name}`);
	let ok;

	switch (name) {
	case 'dae':
		ok = run(`rm -rf ${saved} && mkdir -p ${saved} && cp -a /etc/dae/. ${saved}/`);
		break;

	case 'pods':
		ok = run(`rm -rf ${saved} && mkdir -p ${saved} && { [ ! -d '${PODS}' ] || cp -a '${PODS}/.' ${saved}/; }`);
		break;

	default:
		ok = run(`rm -rf ${saved} && mkdir -p ${saved} && cp -a /etc/config/. ${saved}/`);
	}

	if (!ok)
		fail(`${name}: cannot save its files`);
}

function restore(name) {
	let saved = quoted(`${PUSH}/saved/${name}`);

	switch (name) {
	case 'dae':
		run(`rm -rf /etc/dae/* && cp -a ${saved}/. /etc/dae/`);
		break;

	case 'pods':
		run(`rm -rf '${PODS}'/* && cp -a ${saved}/. '${PODS}/'`);
		break;

	default:
		run(`cp -a ${saved}/. /etc/config/`);
	}
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
		if (!run(`cp ${quoted(`${files}/login`)} ${STATE}/tailscale.login`))
			fail('tailscale: cannot write its login');
		break;

	default:
		for (let batch in sort(glob(`${files}/*.uci`) ?? []))
			if (!run(`uci batch < ${quoted(batch)}`))
				fail(`${basename(batch)}: uci batch failed`);

		run('uci commit');
	}
}

// reload(name): have the service take its configuration; whether it came back is
// for settle to tell.
function reload(name) {
	switch (name) {
	case 'dae':
		run('/etc/init.d/dae restart');
		break;

	case 'pods':
		if (stat(PODS))
			run('/etc/init.d/wrt-containers restart');
		break;

	case 'smb':
		run('/etc/init.d/ksmbd restart');
		break;

	case 'tailscale':
		// The login's options are separate words.
		run(`tailscale up --reset ${trim(readfile(`${STATE}/tailscale.login`) ?? '')} --timeout=60s`);
		break;

	case 'network':
		run('/etc/init.d/network reload');
		break;

	default:
		run('reload_config');
	}
}

// back(name): the service is back after its reload.
function back(name) {
	switch (name) {
	case 'dae':
		return system('/etc/healthcheck.d/50-dae >/dev/null 2>&1') == 0;

	case 'network':
		let connection = ubus.connect();
		let lan = connection?.call('network.interface.lan', 'status');

		connection?.disconnect();

		return lan?.up == true;

	case 'tailscale':
		return system('tailscale status >/dev/null 2>&1') == 0;

	default:
		return true;
	}
}

// settle(name): wait until the service is back; true if it came back in time.
function settle(name) {
	for (let waited = 0; waited <= WAIT; waited += 2) {
		if (back(name))
			return true;

		sleep(2000);
	}

	return false;
}

function apply(name) {
	save(name);
	write(name);
	reload(name);

	if (settle(name)) {
		mkdir(STATE);
		writefile(`${STATE}/${name}`, readfile(`${NEW}/${name}.sha256`) ?? '');

		return;
	}

	restore(name);
	reload(name);
	settle(name);
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
