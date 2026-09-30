# Design

## Context

For motivation, see proposal.md. The following current behavior was checked against the upstream source (OpenWrt main `1019293`):

- **How the apk index is signed**: The index is signed by `apk mkndx --sign $(BUILD_KEY_APK_SEC)` (`package/Makefile:86-95,195-200`). The private key is `$(TOPDIR)/private-key.pem`; if the file does not exist, a prime256v1 key is generated automatically. The public key is derived from the private key (`package/Makefile:77-81`, `rules.mk:350-351`).
- **The build key is installed into the image**: When `CONFIG_BUILDBOT` is off, base-files installs the build public key into the image's `/etc/apk/keys/` (`package/base-files/Makefile:124-128`).
- **What official builds do**: They enable `CONFIG_BUILDBOT` and provide the release public key through the `openwrt-keyring` package (`package/system/openwrt-keyring/Makefile:33-37`).
- **Other side effects of `CONFIG_BUILDBOT`**:
  - In `PER_FEED_REPO` mode, the generated feed list gains an extra kmods path (`include/feeds.mk:40-56`). This design overwrites the whole list, so this has no effect.
  - When the git revision of the toolchain directory changes, the toolchain is forcibly cleaned and rebuilt (`toolchain/Makefile:65-75`). This matches the foundation design, which keys the cache on the toolchain inputs.
- **Firmware signing**: `CONFIG_SIGN_FIRMWARE` uses usign/ucert to sign the firmware metadata (`include/image-commands.mk:94,125`). The rockchip `platform.sh` requires firmware to carry metadata (`REQUIRE_IMAGE_METADATA=1`).
- **Prerequisites provided by earlier changes**:
  - `r4s-build-foundation` produces unsigned artifacts and `manifest.json`;
  - `r4s-ab-rollback` provides writing to the inactive slot and `wrt-slot`;
  - `r4s-services` provides the data disk, podman, and declarative Pods;
  - `r4s-ebpf-datapath` routes container traffic through dae;
  - the foundation's emulation environment and test framework, plus the ISP, internet, and data disk that later changes add.

## Goals / Non-Goals

**Goals:**
- Even if the build job is compromised, an attacker cannot obtain a key that lets them impersonate the publisher long term.
- Device-side updates do not depend at all on the router connecting directly to GitHub.
- The weekly bump has a verification gate: the full upgrade from the previous stable release to the candidate is rehearsed automatically in the CI emulator, with no device needed. Humans only approve the signing and click merge.
- The signing, publishing, sync, and push logic all have automated tests in the emulator or on the host; CI and the tests call the same scripts and differ only in the keys they use.

**Non-Goals:**
- Guaranteeing the integrity of the current build's own artifacts when the build job is compromised. That requires reproducible builds plus comparison against third-party rebuilds, which is out of scope for this change.
- Running our own package repository server or CDN.
- Bulk management of multiple devices.

## Decisions

### D1. Two build variants and the trust anchor

- **The CI build is the release build**: `config/ci.seed` adds the lines below, and there is no separate release profile. As a result, the image CI builds, the image the emulator tests, and the image that is signed and published are always the same. The two profiles are symmetric: `dev` trusts the local build key, and `ci` trusts the release public key.

```
CONFIG_BUILDBOT=y
# CONFIG_PACKAGE_openwrt-keyring is not set
CONFIG_PACKAGE_wrt-keyring=y
# CONFIG_SIGN_FIRMWARE is not set
```

- **`BUILDBOT`'s other defaults**: `BUILDBOT` also turns on the SDK, the image builder, the toolchain archive, the target-wide package set (`ALL_NONSHARED`) and the kernel debug archive. `ci.seed` turns them off again: none of them is published, and each costs build time.

- **The `wrt-keyring` package**: Lives in the project's own feed and installs `/etc/apk/keys/wrt-release-<id>.pem` (the EC public key used by apk) and the usign public key. It can hold several keys at once for rotation.
- **Signing during the build**: The build still generates a one-time apk private key for installs and indexing inside the build. Because `BUILDBOT` is enabled, that key's public key does not enter the image. The build does not sign the firmware either.
- **Development builds**: The dev profile does not enable `BUILDBOT` and keeps the upstream behavior, so the image trusts the locally built key. These images are for debugging only and are never published.
- **Impact on existing tests**: The foundation test "Install a kmod from the same build" switches to the `signed_repo` fixture. This fixture re-signs the current build's repository with an ephemeral key, and the router's snapshot trusts the ephemeral public keys instead of the image's (see D7).
- **Every image requires signed upgrades**: `/lib/upgrade/wrt-release.sh` (in `files/`, so in every profile) sets sysupgrade's own `REQUIRE_IMAGE_SIGNATURE=1`. A dev image therefore also refuses unsigned upgrade images; the tests sign theirs with `release-sign.sh` (D7).
- **Alternatives**:
  - Patch base-files to skip installing the build public key. Rejected, because upstream already provides the ready-made `BUILDBOT` path.
  - Add a separate release profile. Rejected, because then the image CI tests and the image that is published would not be the same.

### D2. Signing job

```
job sign  (needs: firmware; environment: release-signing -> required reviewer)
  1. download unsigned artifacts + manifest.json from the firmware job
  2. verify every artifact's sha256 against manifest.json  (mismatch -> abort)
  3. nix run .#sign-tools   (apk-tools v3, usign, ucert, fwtool built by Nix from
                             pinned first-party sources; no package build, no feeds)
  4. scripts/release-sign.sh <in> <out> --apk-key $APK_KEY --fw-key $FW_KEY
       apk adbsign every packages.adb; usign + ucert + fwtool on factory image and upgrade tar;
       usign manifest.json (manifest.json.sig, what devices trust a release by);
       verify the result against the public keys shipped in wrt-keyring; write SHA256SUMS
  5. upload signed set for upgrade-drill and publish
```

- **When it runs**: `sign` needs `system-test`, and runs only on main and `bump/*`, never for a pull request, and only while the repository variable `RELEASE_SIGNING` is `enabled`. The variable is set once the release keys are in the environment (Migration Plan), so the pipeline runs green before the keys exist.
- **The firmware certificate**: Each signing issues a new ucert certificate for the firmware key, valid from the signing time for one year, and appends the image's signature to it. ucert checks the validity against the device clock, so a device accepts an upgrade only once its clock has passed the signing time, which NTP ensures on a device in service. (`ucert -A` reports failure after it has appended; the script checks the result by verifying it instead.)

- **Where the signing tools come from**: The flake builds the signing tools itself from pinned sources and does not use the host tools produced by the build job. Those tools come from a job that may be compromised, so signing with them would bypass the isolation.
- **One signing script**: `release-sign.sh` takes only an input directory, an output directory, and the two keys. CI passes the production keys; tests pass ephemeral keys and cover the tampering, rotation, and trust anchor scenarios.
- **Key storage**: Both private keys are stored as secrets of the `release-signing` environment, and only that environment can read them. The environment has required reviewers, which satisfies "every signing requires manual approval".
- **Alternatives**:
  - Sign on a local machine. Already ruled out during exploration.
  - Sign in the build job. Rejected; see the proposal for the reasons.

### D3. Publishing

The `publish` job runs after `upgrade-drill` passes (D5). `scripts/release-publish.sh` first assembles the release into a directory and a `release.json` (tag, prerelease flag, notes, attachment list); only the last step uploads it with `gh release create`. The assembly part is covered by host tests.

- **Consistency check**: First confirm that the run identifier in `manifest.json` matches every artifact; abort on a mismatch.
- **Release naming**: The tag is `r<YYYYMMDD>-<openwrt-short-sha>-<run-number>`. PR builds are published as prereleases, and main-branch builds as stable releases.
- **Attachments**: The factory image, the upgrade tar, `repo.tar` (organized in apk's repository directory layout, including targets and packages), `manifest.json`, `manifest.json.sig`, and `SHA256SUMS`. `repo.tar` is not compressed again: the packages in it are compressed already, and the device unpacks it with busybox tar.
- **Upload**: `--upload` runs `gh release create`, with `--prerelease --latest=false` for a candidate and `--latest` for a stable release.
- **Release notes**: Generated automatically from `upstream.lock` and the patch queue hash.
- **Size limit**: Each attachment can be at most 2 GB; the repository archive is expected to be a few hundred MB.

### D4. Device-side sync

```
wrt-sync (procd service, mount trigger /mnt/data/repo; cron daily)
  -> podman run --rootfs /mnt/data/repo/.root  (the router's own programs mounted read-only,
                                               no image; network: podman bridge -> proxied by dae)
       container: query the Releases API (channel: stable | candidate)
                  download manifest.json(.sig), repo.tar and the upgrade tar
                  into /mnt/data/repo/.incoming/<tag>/   (not the factory image)
  -> host side (after container exits 0):
       usign manifest.json.sig with /etc/opkg/keys
       sha256 of the upgrade tar and every index against manifest.json
       apk verify every index with /etc/apk/keys
       mv .incoming/<tag> -> releases/<tag>; ln -sfn releases/<tag> current
       keep newest 3 (by activation), delete older
```

- **Configurable Releases address**: The UCI option `wrt-sync.main.api` defaults to `https://api.github.com`; tests point it at a mock service in the sandbox.
- **The container does not need to be trusted**: The host verifies integrity with the release public keys in the image. The container needs no image at all: its root is an empty directory on the data disk with the router's own `uclient-fetch` and `jsonfilter` mounted read-only, so nothing is pulled and nothing third-party runs. Its only writable mount is `.incoming`.
- **Atomic switch**: A new release is first downloaded to `.incoming`, and the `current` symlink changes only after all checks pass.
- **apk feed list**: `/etc/apk/repositories.d/distfeeds.list` is overwritten to point to the local repository under `current`, as a `file`-style `packages.adb` path.
- **Local upgrade**: `wrt-update` calls sysupgrade to upgrade to the upgrade tar in `current`.
- **Mandatory signature check**: sysupgrade's own `fwtool_check_signature` does the check once `REQUIRE_IMAGE_SIGNATURE=1` (D1): ucert verifies the image's certificate chain with the usign keys in `/etc/opkg/keys`. A missing or wrong signature makes the image invalid; only `sysupgrade -F` would force it, and `wrt-update` never passes it. The A/B change's `platform_check_image` is left as it is.

### D5. Weekly bump

- **Scheduled workflow**: Runs every Monday and reads the HEAD of main in the three upstream repositories. If anything changed, it updates `upstream.lock` and opens a PR from `bump/<date>` with the default token. The PR description includes the old and new SHAs and a `git log --oneline` summary of at most 50 lines. A PR opened with the default token starts no workflows, so the bump workflow starts `check` and `build` on the bump branch itself (`gh workflow run`); their check runs belong to the PR's head commit.
- **PR checks**: The foundation CI fails on a patch conflict and reports the name of the conflicting patch file.
- **Upgrade drill gate**: A ruleset on main requires the `check` and `upgrade-drill` checks (administrators may bypass it). `upgrade-drill` runs after signing and uses the production-signed artifacts and the production trust anchor. Its base is made by `just drill-base`: the latest stable release's factory image with this build's `u-boot-qemu.bin`, which the emulator boots:

```
build.yml   host-toolchain -> firmware (ci) -> system-test (emulation, ephemeral keys)
            -> sign (release-signing, approval; bump PRs and main only)
            -> upgrade-drill -> publish (PR: prerelease, main: release)

upgrade-drill (emulation):
  base      = factory image of the latest stable release (or of this build if none exists yet)
  isp/inet  = datapath topology + fake GitHub Releases API serving this signed candidate
  steps     = push test config -> wrt-sync --candidate -> wrt-update -> reboot
              -> health check confirms the new slot -> config still present
  pass      = new slot confirmed; fail = rollback observed, job fails, nothing is published
```

- **Why device verification is no longer needed**: Device verification was meant to confirm three things: the old system accepts and writes the new image, the new system boots and passes the health check, and the configuration carries over. The drill does all three on the same shipped image with the same trust anchor. The only thing the emulator cannot cover is the hardware path, and A/B rollback is already the safety net for that.
- **Alternatives**:
  - The maintainer verifies on the device and then writes a status (the original plan). Rejected, because it needs work on the device every week.
  - The device reports verification results automatically. Rejected, because the device would need to hold a token that can write GitHub statuses, which increases the attack surface.

### D6. Config push

- **Private repository layout**:

```
wrt-config (private repo)
  .sops.yaml                  age recipient (your workstation key)
  secrets/secrets.enc.yaml    pppoe, wg key, tailscale authkey + login server, smb users
  dae/*.dae.enc               user dae config (no lan_interface / wan_interface), encrypted:
                              its nodes and subscriptions are secrets
  pods/*.yaml                 pod specs
  uci/*.uci.tmpl              uci batch templates; @path@ is filled from the secrets at push time
```

- **Skeleton**: `scripts/config-init.d/` holds the skeleton as plain files; `config-init` copies it, encrypts the secrets and the dae configuration with sops for the recipient in `.sops.yaml`, and commits.

- **Commands**: `just config-init` generates the private repository skeleton; `just config-push <host>` performs the push, with the private repository location given by `WRT_CONFIG_DIR`. Both share their names with their scripts, following the foundation's "object-verb" naming rule. The push runs these steps in order:
  1. Decrypt with sops into a temporary directory, which is cleaned up on exit;
  2. Render the templates;
  3. Transfer the files to `/tmp/wrt-push` on the device over SSH with key authentication only (`BatchMode`, `PasswordAuthentication=no`, `PreferredAuthentications=publickey`, and `IdentitiesOnly` with `--identity`);
  4. Validate on the device without changing anything: `dae validate` in a scratch directory set up as the dae service sets up its own (the firmware's `lan_interface` and DNS listener, an include of the configuration file), and each `uci batch` on a copy of `/etc/config`. A rejected push removes `/tmp/wrt-push` and changes nothing else;
  5. Compare each service's hash with the one recorded in `/etc/wrt-config/<service>` at its last push, and write and reload only the services that changed;
  6. Wait until each reloaded service is back (dae: its health check; network: the LAN up; tailscale: logged in). If it is not, restore its pre-push files, reload it again, and exit with a nonzero status.
- **The device side**: `scripts/config-push.d/device.sh` is sent over SSH for each step (`sh -s -- validate | hashes | apply <service>`), so the image carries nothing of the push.
- **Preservation across upgrades**: What the push writes outside `/etc/config` (`/etc/dae/`, `/etc/tailscale/`, and `/etc/wrt-config/` with the hashes and the tailnet login) is listed in the image's `/lib/upgrade/keep.d/wrt-config`, sysupgrade's own list of what the backup keeps, so it survives A/B upgrades; the uci configuration, the SMB user database and `/etc/passwd` are kept as conffiles already. The Pods live on the data disk.
- **Why encrypt**: If the private repository leaks or is made public by mistake, every plaintext secret is exposed. sops with age fits the Nix ecosystem, and decryption happens only on the workstation. This is a default security measure added by this design; exploration only confirmed "secrets live in a private repository".

### D7. Verification

- **Tests map one-to-one to specs**:
  - `tests/release/test_signing.py`: One part runs on the host: it statically audits the workflows (only `sign` references `release-signing`, and the signing job's only steps are the download, `sign-tools`, and `release-sign.sh`) and drives `release-sign.sh` with ephemeral keys. The other part confirms in the emulator that the device rejects an index signed with another key.
  - `tests/release/test_publishing.py`: Drives `release-publish.sh` on the host, covering the attachments, the prerelease versus stable decision, a run identifier mismatch, and the release notes.
  - `tests/release/test_device_sync.py`: An emulator test. A stand-in for GitHub's Releases API runs in `inet` (HTTPS, with a certificate issued by the test CA, one directory per repository as on GitHub); dae routes it through the proxy, and the ISP blocks direct connections from the router's WAN address to it.
  - `tests/release/test_upstream_bump.py`: Uses local bare repositories on the host as the three upstreams and covers opening a PR, not opening a PR, and patch conflicts; the two upgrade drill scenarios are tagged by the tests that `upgrade-drill` runs.
  - `tests/ops/test_config_push.py`: Runs `just config-push` against the router in the emulator, using a throwaway config repository and an age test key.
- **Ephemeral key fixtures**: `wrt_tests/keys.py` generates a one-time apk EC key and usign key (`release_keys`), and:
  - `signed_repo`: re-signs the current build's artifacts with `release-sign.sh`;
  - the router's snapshot trusts the matching public keys (`install_trust`), in place of the image's own in `/etc/apk/keys` and `/etc/opkg/keys`, as a release image trusts the release keys.
  - With `WRT_SIGNED` naming a production-signed build (the `upgrade-drill` job), nothing is signed and the image's own trust anchors decide.
- **What the emulator lacks**: The harness logs in with a key of its own, authorized in the snapshot, because the config push tests give root a password. The emulated internet has no time server and a snapshot restore rewinds the clock, so the harness sets the router's clock after every boot and restore, as NTP does on a device in service (the firmware certificate is valid from the signing time, D2).
- **Drill tests**: The tests run by the `upgrade-drill` job carry a `drill` marker and are selected separately with pytest's `-m drill`. `system-test` runs the same tests with ephemeral keys, so the drill logic itself is tested on every commit; after signing, the same tests simply run again with the production keys and the production trust anchor.
- **GitHub-side settings**: The environment reviewers and the branch protection required checks are GitHub repository settings, not code. `scripts/github-audit.sh` reads and checks them with `gh api`, and runs periodically in the check workflow.
- **Device**: no step needs the device; every scenario runs in the emulator or on the host.

## Risks / Trade-offs

- **[If the build job is compromised, the current artifacts may already be tampered with]** Signing isolation cannot prevent this. → Long term, reproducible builds and comparison against third-party rebuilds can detect it; short term, manual approval plus reading the diff are the safeguard.
- **[GitHub API rate limiting or throttling]** → Sync runs once a day and makes one API request; a release it has already is not downloaded again.
- **[Arguments and behavior of `apk adbsign`]** → The last step of `release-sign.sh` verifies with the public keys in `wrt-keyring` and treats a failed check as a failure; `test_signing.py` covers this path.
- **[The previous stable release used for the drill is itself defective]** For example, if the old release's upgrade logic has a bug, the drill keeps failing. → The maintainer then decides, and ships an interim release after the fix; the drill baseline is always the latest stable release.
- **[The emulator cannot cover the hardware path]** → A/B rollback is the safety net: if the device fails to boot after an upgrade, it automatically returns to the previous slot.
- **[Forced toolchain rebuilds triggered by `BUILDBOT`]** They happen only when the git revision of the toolchain directory changes, which matches the caching strategy.
- **[Mistakes when pushing configuration by hand]** → Pre-push validation, reloading only the services that changed, and rollback on failure work together.
- **[Losing the age private key makes the secrets undecryptable]** → Keep an offline backup of the age key outside the workstation, documented in `docs/ops.md`.

## Migration Plan

1. Set up GitHub: the `release-signing` environment with the maintainer as required reviewer and `main` and `bump/*` as its only deployment branches, and a ruleset on main requiring `check` and `upgrade-drill`. `just github-audit` reads them back.
2. The maintainer generates the release apk EC key pair and usign key pair with `just release-keys --upload` on their own machine: the private keys go to the environment's secrets and an offline backup, never into the repository; the public keys go into `wrt-keyring` and are committed.
3. Set the repository variable `RELEASE_SIGNING` to `enabled`: from then on main and bump builds are signed, drilled and published.
4. Set up the private config repository and the age key (`just config-init`), and migrate the existing configuration into it.
5. After the first stable release passes its upgrade drill, flash its factory image (which already includes `wrt-keyring`) and push the configuration. All later updates go through sync plus `wrt-update`.
6. Rollback: `wrt-slot switch` returns to the previous slot; the local repository keeps the latest 3 releases, so you can also upgrade again to a specific older release.

## Open Questions

- The Release tag format can be adjusted later without affecting the specs.
- The sync container needs no base image (D4).
