# Hand interactive login shells over to zsh. The login shell in /etc/passwd stays
# /bin/ash, so SSH and serial logins keep working if zsh is missing or broken,
# and non-interactive commands (ssh host cmd) never read this file. Only the ash
# login shell is handed over: an explicit `bash -l` stays in bash.
case $- in
	*i*)
		if [ -t 0 ] && [ -z "${ZSH_VERSION:-}${BASH_VERSION:-}" ] && [ -x /usr/bin/zsh ] &&
			/usr/bin/zsh -fc true 2>/dev/null; then
			exec /usr/bin/zsh -l
		fi
		;;
	*) ;;
esac
