# Proposal

## Why

This release pipeline addresses five problems:

- **Signing and distribution must be done in-house.** The kernel is self-built, so only this project can sign and distribute the kmods and firmware.
- **Pulling updates directly from GitHub is unreliable.** dae binds only to the LAN and router-originated traffic goes out directly, so pulling updates straight from GitHub is unstable in mainland China.
- **Signing keys must not touch third-party code.** The build executes a large amount of third-party Go and Rust code, and the signing keys must not be present in any job that runs that code.
- **Tracking upstream needs a controlled cadence.** Tracking main every week requires a low-risk "verify, then merge" process.
- **Runtime secrets must not be public.** PPPoE accounts, dae subscriptions, WireGuard private keys, and Tailscale authentication must not appear in the public repository or in images.

## What Changes

- **Build variant**: The CI build is the release build (the `ci` profile enables `BUILDBOT` and swaps in the project's own public key), so the emulator tests exactly the image that will be signed and released.
- **Signing**
  - CI gets a separate signing job that only signs build artifacts and executes no third-party code.
  - The signing keys for the apk repository and the firmware are kept in a GitHub protected environment, and every signing requires manual approval.
  - The signing tools (apk-tools, usign, ucert, fwtool) are built separately by Nix from pinned sources, not taken from binaries produced by the build job.
  - Following the official approach: enable `CONFIG_BUILDBOT` so the key generated temporarily at build time stays out of the image, then provide the release public key through the project's own `wrt-keyring` package, which does not include the official OpenWrt public keys.
  - The signing logic lives in a single script; CI uses the production keys and tests use ephemeral keys.
- **Publishing**: The signed single-slot upgrade image, the factory image, and the apk repository containing all kmods are published together to GitHub Releases.
- **Device-side sync**
  - A container runs on the router; its traffic goes through the dae proxy via podman0, and it syncs Release artifacts to `/mnt/data/repo`.
  - apk installs packages from this local repository, and sysupgrade writes the inactive slot from a local file.
  - The signing public key is preinstalled in the image.
  - When the data disk is absent, only package installation and upgrades are unavailable; the installed system keeps running normally.
- **Weekly upstream tracking**
  - A bot updates `upstream.lock` once a week and opens a PR.
  - After signing, CI runs an upgrade drill in the emulator: starting from the previous stable release, it syncs and upgrades to the candidate, and the merge is allowed only after the health check confirms it. No work on the device is needed each week.
  - If patches such as BBRv3 fail to apply, CI fails immediately.
- **Config push**
  - A private config repository holds secrets and runtime configuration, including config.dae. Secrets are encrypted with sops + age before they are committed and are decrypted only on the workstation.
  - A push script writes to the router over SSH and triggers a reload of the affected services.
  - No secrets appear in the public repository or in images.

## Capabilities

### New Capabilities

- `release/signing`: How the signing job is isolated, where the keys are stored, and the approval process.
- `release/publishing`: Which artifacts are published, where they are published, and how they are organized.
- `release/device-sync`: How the device syncs artifacts through the proxy to a local repository, and how apk and sysupgrade use the local artifacts.
- `release/upstream-bump`: The weekly lock file update PR, the verify-then-merge cadence, and how patches that fail to apply are handled.
- `ops/config-push`: The private config repository, and how secrets and runtime configuration are pushed and applied.

### Modified Capabilities

(None.)

## Impact

- **GitHub**: Actions, protected environments, Releases, scheduled workflows, and a bot that opens PRs.
- **New**: The private config repository, plus the corresponding `just config-init` and `just config-push`.
- **Verification**: Signing, release assembly, and the upstream bump are covered by host tests; device sync, upgrade, and config push run in the emulator against the shipped image, with the Releases service mocked in the sandbox. No step needs the device.
- **Device side**: The sync container, the local apk repository configuration, and the preinstalled signing public key.
- **Depends on other changes**:
  - `r4s-build-foundation`: CI and build artifacts.
  - `r4s-ab-rollback`: Writing the inactive slot, and rollback.
  - `r4s-services`: The data disk and podman.
  - `r4s-ebpf-datapath`: Container traffic through the dae proxy.
