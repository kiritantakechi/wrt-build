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

- **The `wrt-keyring` package**: Lives in the project's own feed and installs `/etc/apk/keys/wrt-release-<id>.pem` (the EC public key used by apk) and the usign public key. It can hold several keys at once for rotation.
- **Signing during the build**: The build still generates a one-time apk private key for installs and indexing inside the build. Because `BUILDBOT` is enabled, that key's public key does not enter the image. The build does not sign the firmware either.
- **Development builds**: The dev profile does not enable `BUILDBOT` and keeps the upstream behavior, so the image trusts the locally built key. These images are for debugging only and are never published.
- **Impact on existing tests**: The foundation test "Install a kmod from the same build" switches to the `signed_repo` fixture. This fixture re-signs the current build's repository with an ephemeral key and writes the ephemeral public key into the test overlay (see D7).
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
       verify the result against the public keys shipped in wrt-keyring; write SHA256SUMS
  5. upload signed set for upgrade-drill and publish
```

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
- **Attachments**: The factory image, the upgrade tar, `repo.tar.zst` (organized in apk's repository directory layout, including targets and packages), `manifest.json`, and `SHA256SUMS`.
- **Release notes**: Generated automatically from `upstream.lock` and the patch queue hash.
- **Size limit**: Each attachment can be at most 2 GB; the repository archive is expected to be a few hundred MB.

### D4. Device-side sync

```
wrt-sync (procd service, mount trigger /mnt/data)
  -> podman kube play pods/wrt-sync.yaml   (image: minimal curl+jq, network: podman bridge
                                             -> proxied by dae)
       container: query GitHub Releases API (channel: stable | candidate)
                  download assets into /mnt/data/repo/.incoming/<tag>/
  -> host side (after container exits 0):
       verify sha256 against manifest.json  AND  apk index signature with /etc/apk/keys
       mv .incoming/<tag> -> releases/<tag>; ln -sfn releases/<tag> current
       keep newest 3, delete older
cron: daily
```

- **Configurable Releases address**: The UCI option `wrt-sync.main.api` defaults to `https://api.github.com`; tests point it at a mock service in the sandbox.
- **The container does not need to be trusted**: The host verifies integrity with the release public key in the image. So the sync container can use a minimal third-party image; its only job is downloading.
- **Atomic switch**: A new release is first downloaded to `.incoming`, and the `current` symlink changes only after all checks pass.
- **apk feed list**: `/etc/apk/repositories.d/distfeeds.list` is overwritten to point to the local repository under `current`, as a `file`-style `packages.adb` path.
- **Local upgrade**: `wrt-update` calls sysupgrade to upgrade to the upgrade tar in `current`.
- **Mandatory signature check**: `platform_check_image` (from the A/B change) additionally requires the image to carry a valid signature. On top of `REQUIRE_IMAGE_METADATA`, it uses ucert to verify against the public key in the image.

### D5. Weekly bump

- **Scheduled workflow**: Runs every Monday and reads the HEAD of main in the three upstream repositories. If anything changed, it updates `upstream.lock` and opens a PR with a GitHub App or the default token. The PR description includes the old and new SHAs and a `git log --oneline` summary of at most 50 lines.
- **PR checks**: The foundation CI fails on a patch conflict and reports the name of the conflicting patch file.
- **Upgrade drill gate**: Branch protection requires the `upgrade-drill` job to pass. It runs after signing and uses the production-signed artifacts and the production trust anchor:

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
  .sops.yaml                  age recipients (your workstation key)
  secrets/*.enc.yaml          pppoe, dae subscriptions, wg keys, tailscale authkey, smb users
  dae/*.dae(.enc)             user dae config (no lan_interface / wan_interface)
  pods/*.yaml                 pod specs
  uci/*.uci.tmpl              uci batch templates, filled from secrets at push time
```

- **Commands**: `just config-init` generates the private repository skeleton; `just config-push <host>` performs the push, with the private repository location given by `WRT_CONFIG_DIR`. Both share their names with their scripts, following the foundation's "object-verb" naming rule. The push runs these steps in order:
  1. Decrypt with sops into a temporary directory, which is cleaned up on exit;
  2. Render the templates;
  3. Validate locally: `uci` syntax checks, plus a pre-validation with `dae validate` on the device. The pre-validation runs in a temporary directory on the device and changes no existing configuration;
  4. Compute a configuration hash for each service, compare it with the record on the device, and push and reload only the services that changed;
  5. Transfer the files to the device over `ssh -o PasswordAuthentication=no` and run `uci batch`;
  6. If a service fails to reload, restore its pre-push backup, reload it again, and exit with a nonzero status.
- **Preservation across upgrades**: The paths the push writes (`/etc/dae/user/`, the relevant entries in `/etc/config/*`, and local files other than the Pod YAML) are appended to the image's `/etc/sysupgrade.conf` so they survive A/B upgrades.
- **Why encrypt**: If the private repository leaks or is made public by mistake, every plaintext secret is exposed. sops with age fits the Nix ecosystem, and decryption happens only on the workstation. This is a default security measure added by this design; exploration only confirmed "secrets live in a private repository".

### D7. Verification

- **Tests map one-to-one to specs**:
  - `tests/release/test_signing.py`: One part runs on the host: it statically audits the workflows (only `sign` references `release-signing`, and the signing job's only steps are the download, `sign-tools`, and `release-sign.sh`) and drives `release-sign.sh` with ephemeral keys. The other part confirms in the emulator that the device rejects an index signed with another key.
  - `tests/release/test_publishing.py`: Drives `release-publish.sh` on the host, covering the attachments, the prerelease versus stable decision, a run identifier mismatch, and the release notes.
  - `tests/release/test_device_sync.py`: An emulator test. A mock GitHub Releases API runs in `inet` (HTTPS, with a certificate issued by the test CA), while direct connections from the router's WAN address to it are blocked.
  - `tests/release/test_upstream_bump.py`: Uses local bare repositories on the host as the three upstreams and covers opening a PR, not opening a PR, and patch conflicts; the two upgrade drill scenarios are tagged by the tests that `upgrade-drill` runs.
  - `tests/ops/test_config_push.py`: Runs `just config-push` against the router in the emulator, using a throwaway config repository and an age test key.
- **Ephemeral key fixtures**: `wrt_tests/keys.py` generates a one-time apk EC key and usign key and provides two fixtures:
  - `signed_repo`: re-signs the current build's artifacts with `release-sign.sh`;
  - `trust`: writes the matching public keys into the router's test overlay, replacing the existing public keys in `/etc/apk/keys`.
- **Drill tests**: The tests run by the `upgrade-drill` job carry `@target("emulation")` and are selected separately with pytest's `-m drill`. `system-test` runs the same tests with ephemeral keys, so the drill logic itself is tested on every commit; after signing, the same tests simply run again with the production keys and the production trust anchor.
- **GitHub-side settings**: The environment reviewers and the branch protection required checks are GitHub repository settings, not code. `scripts/github-audit.sh` reads and checks them with `gh api`, and runs periodically in the check workflow.
- **Device**: This change has no device-only scenarios.

## Risks / Trade-offs

- **[If the build job is compromised, the current artifacts may already be tampered with]** Signing isolation cannot prevent this. → Long term, reproducible builds and comparison against third-party rebuilds can detect it; short term, manual approval plus reading the diff are the safeguard.
- **[GitHub API rate limiting or throttling]** → Sync runs once a day and uses conditional requests (ETag).
- **[Arguments and behavior of `apk adbsign`]** → The last step of `release-sign.sh` verifies with the public keys in `wrt-keyring` and treats a failed check as a failure; `test_signing.py` covers this path.
- **[The previous stable release used for the drill is itself defective]** For example, if the old release's upgrade logic has a bug, the drill keeps failing. → The maintainer then decides, and ships an interim release after the fix; the drill baseline is always the latest stable release.
- **[The emulator cannot cover the hardware path]** → A/B rollback is the safety net: if the device fails to boot after an upgrade, it automatically returns to the previous slot.
- **[Forced toolchain rebuilds triggered by `BUILDBOT`]** They happen only when the git revision of the toolchain directory changes, which matches the caching strategy.
- **[Mistakes when pushing configuration by hand]** → Pre-push validation, reloading only the services that changed, and rollback on failure work together.
- **[Losing the age private key makes the secrets undecryptable]** → Keep an offline backup of the age key outside the workstation, documented in `docs/ops.md`.

## Migration Plan

1. Generate the release apk EC key pair and usign key pair. Store the private keys as secrets of the `release-signing` environment, and put the public keys into `wrt-keyring`.
2. Set up the private config repository and the age key, and migrate the existing configuration into it.
3. After the first stable release, flash the factory image (which already includes `wrt-keyring`) and run `just test-device` once. All later updates go through sync plus `wrt-update`.
4. Rollback: `wrt-slot switch` returns to the previous slot; the local repository keeps the latest 3 releases, so you can also upgrade again to a specific older release.

## Open Questions

- The Release tag format can be adjusted later without affecting the specs.
- For the sync container's base image, pick a minimal, well-maintained image during implementation; this does not affect the specs.
