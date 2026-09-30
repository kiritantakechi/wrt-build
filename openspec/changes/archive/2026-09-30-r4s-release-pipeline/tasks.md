# Tasks

## 1. Trust anchor and build variants

- [ ] 1.1 Generate the release apk EC key pair (prime256v1) and usign key pair. Store the private keys as secrets of the GitHub `release-signing` environment, and set required reviewers on that environment. Verification: `scripts/github-audit.sh` reads back the environment and its approval rules; no repository file contains a private key (the gitleaks scan in `just check` passes).
- [ ] 1.2 Add `wrt-keyring` to the project's own feed; it installs the apk public key and the usign public key and supports multiple keys. Verification: the "Check trust anchors in the image" test in `test_signing.py` reads the image audit output and sees only these public keys.
- [ ] 1.3 In `config/ci.seed`, add `BUILDBOT`, remove `openwrt-keyring`, add `wrt-keyring`, and leave `SIGN_FIRMWARE` off (design D1). Verification: in the image built by CI, `/etc/apk/keys` contains only the release public keys and no keys starting with `local-*` or `openwrt-*`.
- [x] 1.4 Build the signing tools `.#sign-tools` with the flake (apk-tools v3, usign, ucert, fwtool, all from pinned sources). Verification: `nix run .#sign-tools -- --version` lists the versions of all four tools.
- [ ] 1.5 Implement ephemeral keys (`wrt_tests/keys.py`), the `release_keys` and `signed_repo` fixtures and a router snapshot that trusts the ephemeral keys (`install_trust`); switch the foundation test that installs a kmod to `signed_repo`. Verification: `tests/unit/test_keys.py` signs and verifies once with a generated key; `firmware/test_kernel.py` still passes on the ci build.

## 2. Signing and publishing

- [x] 2.1 Implement `scripts/release-sign.sh`: check the sha256 values in the manifest, sign the indexes with `apk adbsign`, sign the images with usign, ucert, and fwtool, verify once with the supplied public keys, and write `SHA256SUMS`. Verification: `tests/release/test_signing.py` uses ephemeral keys to cover three scenarios: "Artifact does not match the manifest", "Signed package index", and "Rotation transition period".
- [x] 2.2 Write the `sign` job, which references only the `release-signing` environment and whose only steps are downloading the artifacts, `nix run .#sign-tools`, and `release-sign.sh`. Verification: the workflow audit tests in `test_signing.py` cover "Check build job permissions" and "Check what the signing job runs"; the "No approval" scenario is guaranteed by GitHub environment protection, registered in `verified-elsewhere.toml`, and checked by `github-audit.sh`.
- [x] 2.3 Implement `scripts/release-publish.sh`: check the run identifier, assemble the attachments and `release.json` (tag, prerelease flag, notes), and finally call `gh release create`. Write the `publish` job, ordered after `upgrade-drill`. Verification: `tests/release/test_publishing.py` covers every scenario in the publishing spec (the upload step is judged by the assembled output, without actually calling GitHub).
- [x] 2.4 Implement `scripts/github-audit.sh`, which checks the environment reviewers and the branch protection required checks (including `upgrade-drill`), and add it to the scheduled run of the check workflow. Verification: running it on this repository gives the expected output; running it on a test repository that deliberately lacks reviewers fails.

## 3. Device-side sync and upgrade

- [x] 3.1 Implement `wrt-sync` in the project's own feed: a procd service plus a mount trigger that downloads in a container (no image: the router's own programs, read-only, design D4), verifies on the host, then atomically switches `current`, keeps only 3 releases, supports the stable and candidate channels, and has a configurable Releases address; it also ships a daily cron job. Verification: covered by the sync scenarios in `test_device_sync.py`.
- [x] 3.2 Overwrite the apk feed list to point to the local `current`. Verification: covered by the "Install a kmod with WAN down" and "No data disk attached" tests.
- [x] 3.3 Implement `wrt-update`, and enforce signature verification with sysupgrade's own `REQUIRE_IMAGE_SIGNATURE` (design D4). Verification: covered by the "Tampered image" test; an additional test confirms that an unsigned image is rejected as well.
- [x] 3.4 Implement a mock GitHub Releases API in `wrt_tests/`: it lives in `inet`, serves HTTPS with a certificate issued by the test CA, and takes its data from a `release.json` and attachments in a directory; it can drop connections midway, to test interrupted syncs. Verification: `tests/unit/test_releases.py` accesses it with curl, and listing, downloading, and disconnecting all behave as expected.

## 4. Weekly bump and upgrade drill

- [x] 4.1 Implement `scripts/upstream-bump.sh` and the scheduled workflow: check the three upstream repositories and, when there are updates, open a PR with the old and new SHAs and a commit summary in the PR description; open none when there are no updates. Verification: `tests/release/test_upstream_bump.py` uses local bare repositories as the upstreams and covers the "Upstream has updates" and "Upstream has no updates" scenarios (the PR-opening step checks only the generated title and description); the patch conflict scenario drives `patch.sh` with a fake upstream that conflicts with a patch and confirms that the failure message includes the patch file name.
- [x] 4.2 Write the `upgrade-drill` job and the `-m drill` tests: take the factory image of the latest stable release (or this build's factory image if there is no stable release yet), push the test configuration, sync the candidate, run `wrt-update`, and wait for the health check to confirm. `system-test` runs the same tests with ephemeral keys. Verification: "Drill passes" passes in `system-test`; the "Candidate fails the health check" test puts a check that always fails into the preserved configuration and confirms that the device returns to its original slot and the test judges the drill as failed.
- [x] 4.3 Configure branch protection to make `upgrade-drill` a required check. Verification: `github-audit.sh` detects this check; a PR whose drill fails cannot be merged.
- [ ] 4.4 Write `docs/release-flow.md`: bump PR → signing approval → upgrade drill → candidate release → merge → main-branch signing approval → drill → stable release → device sync and `wrt-update`. Verification: the first real bump follows the document end to end, and the link for each step is recorded in `docs/validation/release.md`.

## 5. Config push

- [x] 5.1 Implement `scripts/config-init.sh` (backing `just config-init`), which generates the skeleton of the private repository `wrt-config` (`.sops.yaml`, `secrets`, `dae`, `pods`, `uci` templates) and an age key; add `sops` and `age` to both flake devShells. Verification: `test_config_push.py` runs gitleaks on the generated skeleton and on a fixture repository filled with test secrets and finds no plaintext secrets in the full history; the method for backing up the age key offline is documented in `docs/ops.md`.
- [x] 5.2 Implement `scripts/config-push.sh` (backing `just config-push <host>`): decrypt, render templates, validate locally, pre-validate the dae configuration on the device, reload only the services that changed according to the hashes, roll back on failure, and authenticate only with SSH keys. Verification: `tests/ops/test_config_push.py` pushes to the router in the emulator and covers every scenario in the config-push spec except "Upgrade to the other slot".
- [x] 5.3 Have the upgrade backup keep the paths written by the push (`/lib/upgrade/keep.d/wrt-config` in the image). Verification: covered by the "Upgrade to the other slot" test (a config-preserving A/B upgrade after a push).

## 6. Emulator and host test summary

- [x] 6.1 `tests/release/test_device_sync.py`: covers every scenario in the device-sync spec. For "Router cannot reach GitHub directly", `isp` blocks traffic from the router's WAN address to the mock Releases service; for "Sync interrupted midway", the mock service drops the connection; for "Keep the most recent releases", a fourth release is synced while 3 are present. Verification: all tests pass.
- [x] 6.2 Run `spec-coverage`. Verification: this change has no uncovered scenarios, and only "No approval" is registered in `verified-elsewhere.toml`.

## 7. First rollout

- [ ] 7.1 Following the design's Migration Plan, generate the production keys and complete the first stable release. Verification: its upgrade drill passes in CI with the production keys and trust anchor, which syncs the release with `wrt-sync` in the emulator; the links of each step are recorded in `docs/validation/release.md`. Flashing the router with it is the maintainer's own migration step, described in `docs/release-flow.md`.
