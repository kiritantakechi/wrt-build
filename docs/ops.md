# Operating the router

The router's own configuration and secrets live in a private repository of their own, encrypted, and reach the router with `config-push` (r4s-release-pipeline D6). The image carries none of them, so a new slot gets them from the upgrade's backup and a new router gets them from a push.

## The private repository

`just config-init` makes it: a git repository, outside this one, with the skeleton of `scripts/config-init.d`.

```sh
just config-init ~/wrt-config
export WRT_CONFIG_DIR=~/wrt-config
```

| Path | Holds |
|---|---|
| `.sops.yaml` | the age recipient every file is encrypted for |
| `secrets/secrets.enc.yaml` | the credentials, encrypted: `pppoe.username`, `pppoe.password`, `wireguard.private_key`, `tailscale.auth_key`, `tailscale.login_server`, `smb.users` (a list of `name` and `password`) |
| `dae/*.dae.enc` | dae's configuration, encrypted, since its nodes and subscriptions are secrets: `config.dae.enc`, and any file it includes. Never `lan_interface` or `wan_interface`: the firmware sets them |
| `uci/<config>.uci.tmpl` | uci batches; `@path@` is the secret at that path, e.g. `set network.wan.password='@pppoe.password@'` |
| `pods/*.yaml` | Pod declarations, and a `<pod>.options` beside one where it needs them |

Edit an encrypted file with sops, which decrypts it into a temporary file for the editor and encrypts it again, and commit as usual:

```sh
sops ~/wrt-config/secrets/secrets.enc.yaml
sops ~/wrt-config/dae/config.dae.enc
```

Nothing goes in as plain text: the `.gitignore` keeps out `*.dec` and `*.plain`, and gitleaks finds nothing in the history (`gitleaks git ~/wrt-config`).

## Pushing

```sh
just config-push 192.168.1.1 --identity ~/.ssh/wrt
```

The push logs in as root with that key (or the agent's), never with a password. Put the key's public half in the router's `/etc/dropbear/authorized_keys` first (LuCI: System, Administration, SSH-Keys). Then:

1. The secrets are decrypted into a temporary directory, which goes when the push ends, and the templates are filled in.
2. Everything is checked on the router before anything changes: dae's configuration with `dae validate`, set up as the dae service would run it, and each uci batch on a copy of the configuration. A push that fails here changes nothing.
3. Each service whose files changed since its last push (dae, network and the other uci configurations, tailscale, smb, pods) is written and reloaded, and the push waits until it is back. One that does not come back gets its previous files again and is reloaded with them, and the push fails, naming it.

Pushing the same configuration again reloads nothing. What the push wrote is kept through upgrades: the uci configuration, `/etc/dae`, `/etc/tailscale`, `/etc/wrt-config` (what was last pushed), the SMB users.

## The age key

The age key decrypts every secret, and nothing else does: lose it, and the repository is locked for good. `config-init` makes it at `~/.config/sops/age/keys.txt` (or `$SOPS_AGE_KEY_FILE`) when there is none.

- **Back it up offline** as soon as it exists: the file on a medium kept away from the workstation, or its one `AGE-SECRET-KEY-1...` line printed on paper or in a password manager.
- **Restore** it by writing that line back into `~/.config/sops/age/keys.txt` (mode 600). `age-keygen -y ~/.config/sops/age/keys.txt` prints its recipient, which must be the one in `.sops.yaml`.
- **Replace** it: make a new key with `age-keygen -o`, put its recipient in `.sops.yaml`, re-encrypt each file with `sops updatekeys <file>` while the old key is still in the key file, commit, and back the new key up.
