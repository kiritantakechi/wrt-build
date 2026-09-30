#!/bin/sh
# The router's half of config-push (r4s-release-pipeline D6), sent over SSH.
# Usage: sh -s -- validate | hashes | apply <service>   (in /tmp/wrt-push)
# config-push uploads each service's new files to /tmp/wrt-push/new/<service>:
#  validate      checks them without touching the configuration: dae's in a
#                scratch directory set up as the dae service would (the entry
#                includes dae.config.config_file, and the other files lie next to
#                it), each uci batch on a copy of /etc/config;
#  hashes        prints the hash of each service as last pushed;
#  apply <name>  saves what the service has now, writes the new files, reloads
#                the service and waits for it to come back; if it does not, puts
#                the saved files back, reloads it again and fails.
set -eu

PUSH=/tmp/wrt-push
NEW="${PUSH}/new"
STATE=/etc/wrt-config
PODS=/mnt/data/containers/pods
WAIT=60

fail() {
	echo "config-push: $*" >&2
	exit 1
}

validate() {
	if [ -d "${NEW}/dae" ]; then
		check="${PUSH}/dae-check"
		config=$(uci -q get dae.config.config_file) || config=/etc/dae/config.dae
		[ -f "${NEW}/dae/${config##*/}" ] || fail "dae: ${config##*/} is not among the files"
		rm -rf "${check}"
		mkdir -p "${check}"
		cp "${NEW}/dae"/* "${check}/"
		{
			printf 'global {\n\tlan_interface: br-lan\n}\n'
			printf "dns {\n\tbind: '127.0.0.1:5353'\n}\n"
			printf 'include {\n\t%s\n}\n' "${config##*/}"
		} >"${check}/main.dae"
		chmod 600 "${check}"/*
		dae validate -c "${check}/main.dae" >&2 || fail "dae does not accept the configuration"
	fi
	for batch in "${NEW}"/*/*.uci; do
		[ -e "${batch}" ] || continue
		rm -rf "${PUSH}/uci-check"
		cp -a /etc/config "${PUSH}/uci-check"
		errors=$(uci -c "${PUSH}/uci-check" batch <"${batch}" 2>&1) || errors="${errors:-failed}"
		[ -z "${errors}" ] || fail "${batch##*/}: ${errors}"
	done
}

hashes() {
	mkdir -p "${STATE}"
	for service in "${NEW}"/*/; do
		name=${service%/}
		name=${name##*/}
		last=$(cat "${STATE}/${name}" 2>/dev/null) || last=none
		printf '%s %s\n' "${name}" "${last}"
	done
}

# The files of a service on the router: save_<name>, write_<name>.
save() {
	saved="${PUSH}/saved/$1"
	rm -rf "${saved}"
	mkdir -p "${saved}"
	case "$1" in
		dae) cp -a /etc/dae/. "${saved}/" ;;
		pods) [ ! -d "${PODS}" ] || cp -a "${PODS}/." "${saved}/" ;;
		*) cp -a /etc/config/. "${saved}/" ;;
	esac
}

restore() {
	saved="${PUSH}/saved/$1"
	case "$1" in
		dae)
			rm -rf /etc/dae/*
			cp -a "${saved}/." /etc/dae/
			;;
		pods)
			rm -rf "${PODS:?}"/*
			cp -a "${saved}/." "${PODS}/"
			;;
		*) cp -a "${saved}/." /etc/config/ ;;
	esac
}

write() {
	new="${NEW}/$1"
	case "$1" in
		dae)
			for file in "${new}"/*; do
				cp "${file}" "/etc/dae/${file##*/}"
				chmod 600 "/etc/dae/${file##*/}"
			done
			uci set dae.config.enabled=1
			uci commit dae
			;;
		pods)
			mkdir -p "${PODS}"
			cp "${new}"/* "${PODS}/"
			;;
		smb)
			while read -r user password; do
				grep -q "^${user}:" /etc/passwd ||
					echo "${user}:x:1000:1000::/var:/bin/false" >>/etc/passwd
				grep -q "^${user}:" /etc/group || echo "${user}:x:1000:" >>/etc/group
				ksmbd.adduser -p "${password}" "${user}" >/dev/null
			done <"${new}/users"
			;;
		tailscale) cp "${new}/login" /etc/wrt-config/tailscale.login ;;
		*)
			for batch in "${new}"/*.uci; do
				uci batch <"${batch}"
			done
			uci commit
			;;
	esac
}

# reload <name>: have the service take its configuration; whether it came back
# is for settle to tell.
reload() {
	case "$1" in
		dae) /etc/init.d/dae restart || true ;;
		pods) [ ! -d "${PODS}" ] || /etc/init.d/wrt-containers restart || true ;;
		smb) /etc/init.d/ksmbd restart || true ;;
		tailscale)
			login=$(cat /etc/wrt-config/tailscale.login)
			# shellcheck disable=SC2086 # the login's options are separate words
			tailscale up --reset ${login} --timeout=60s || true
			;;
		network) /etc/init.d/network reload || true ;;
		*) reload_config || true ;;
	esac
}

# settle <name>: wait until the service is back; came_back is yes if it is.
settle() {
	waited=0
	came_back=no
	while [ "${waited}" -le "${WAIT}" ]; do
		case "$1" in
			dae) /etc/healthcheck.d/50-dae >/dev/null 2>&1 && came_back=yes ;;
			network)
				lan=$(ubus call network.interface.lan status 2>/dev/null) || lan=
				state=$(printf '%s' "${lan}" | jsonfilter -e @.up 2>/dev/null) || state=
				[ "${state}" != true ] || came_back=yes
				;;
			tailscale) tailscale status >/dev/null 2>&1 && came_back=yes ;;
			*) came_back=yes ;;
		esac
		[ "${came_back}" = no ] || return 0
		sleep 2
		waited=$((waited + 2))
	done
}

apply() {
	name=$1
	save "${name}"
	write "${name}"
	reload "${name}" >&2
	settle "${name}"
	if [ "${came_back}" = yes ]; then
		mkdir -p "${STATE}"
		cat "${NEW}/${name}.sha256" >"${STATE}/${name}"
		return 0
	fi
	restore "${name}"
	reload "${name}" >&2
	settle "${name}"
	fail "${name} did not come back with the new configuration; the previous one is back"
}

case "${1:-}" in
	validate) validate ;;
	hashes) hashes ;;
	apply) apply "$2" ;;
	*) fail "usage: validate | hashes | apply <service>" ;;
esac
