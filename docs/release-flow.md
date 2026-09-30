# Release flow

How a release gets from upstream to the router (r4s-release-pipeline). Nothing in it needs the R4S: the emulator drills every upgrade before it is published, and the router only syncs and installs what passed.

```
Monday: bump.yml ── upstream moved ──> PR from bump/<date>, check + build on the branch
  build: host-toolchain -> firmware -> system-test
         -> sign            (waits for the maintainer's approval)
         -> upgrade-drill   (the latest stable release upgraded to this candidate)
         -> publish         (a pre-release: the candidate)
  the PR merges once check and upgrade-drill passed
main: the same pipeline -> sign (approval) -> upgrade-drill -> publish (the stable release)
router: wrt-sync (daily, through dae) -> /mnt/data/repo/current -> apk, wrt-update
```

GitHub runs the pipeline and holds the releases; the repository itself lives on Codeberg (codeberg.org/kiritan/wrt-build), and GitHub (github.com/kiritantakechi/wrt-build) mirrors it.

## Step by step

1. **The bump.** Every Monday at 03:23 UTC `.github/workflows/bump.yml` compares the heads of openwrt, packages and luci with `upstream.lock` (`scripts/upstream-bump.sh`). When one moved, it pushes the new lock to `bump/<date>` and opens a pull request that names the old and new commit of each and lists the commits in between. A pull request opened by a workflow starts no workflows, so it starts `check` and `build` on the branch itself; their checks show on the pull request.
2. **The build.** `build.yml` builds the ci profile, the release build, and tests it in the emulator with keys made for the run. A patch that no longer applies fails `firmware` and names the patch.
3. **The signing approval.** `sign` waits for the maintainer: GitHub asks for a review of the `release-signing` deployment in the run's page (Review deployments, then Approve and deploy). Before approving, read the pull request's diff and the build's log. `sign` then runs the pinned signing tools (`nix run .#sign-tools`) on the unsigned artifacts and nothing else; the keys exist only in that environment.
4. **The upgrade drill.** `upgrade-drill` boots the latest stable release in the emulator (this build itself before the first one), pushes a test configuration with `config-push`, syncs the signed candidate with `wrt-sync --candidate`, upgrades with `wrt-update` and waits for the health check to confirm the new slot. The configuration must still be there. A candidate that is never confirmed is rolled back by U-Boot, and the job fails.
5. **The candidate.** `publish` makes the drilled candidate a pre-release: routers on the candidate channel get it, the others do not.
6. **The merge.** main's rules let the pull request merge only after `check` and `upgrade-drill` passed. Merge it on GitHub, then bring main to Codeberg (below).
7. **The stable release.** The push to main runs the pipeline again: another approval, another drill, and `publish` makes it the latest stable release, tagged `r<date>-<openwrt commit>-<run>`. Its notes name the three upstream commits, the patch queue's hash and the kernel.
8. **The router.** At 04:43 every day `wrt-sync` fetches the newest stable release into the data disk, through dae like any LAN traffic; `wrt-update` upgrades to it when you choose.

### Bringing main to Codeberg

A merge on GitHub leaves Codeberg behind. Fetch it and push it on, before anything else goes to main:

```sh
git fetch github main
git merge --ff-only github/main
git push codeberg main
```

Anything pushed to main goes to both remotes, Codeberg first.

## On the router

The router's first release is a flash of the stable release's factory image (`docs/migration-single-to-ab.md`). It trusts the release keys only: the image's `/etc/apk/keys` and `/etc/opkg/keys` hold nothing else (`wrt-keyring`).

```sh
wrt-sync                   # fetch the newest stable release; prints "<tag> is current"
apk add kmod-dummy         # packages and kmods come from the local repository
wrt-update                 # upgrade to the current release (the other slot, on trial)
```

- **The local repository** is `/mnt/data/repo`: `releases/<tag>` for the three latest releases and `current` for the newest. apk reads `current`, so packages install with the WAN down; without the data disk apk finds no repository, and the router goes on routing.
- **Nothing unverified becomes current.** The container fetches the release's manifest and its signature, the package repository and the upgrade image into `.incoming`; the router makes it current only once the manifest's signature verifies with the release keys and every index and the image match the manifest. An interrupted sync leaves the previous release current.
- **Nothing unsigned is installed.** sysupgrade refuses an upgrade image without a valid signature of a release key (`REQUIRE_IMAGE_SIGNATURE`), and `wrt-update` never forces it. The signature's certificate is valid from the moment of signing, so the router's clock must be right: NTP sets it once the WAN is up.
- **Candidates** come only on request: `uci set wrt-sync.main.channel=candidate && uci commit wrt-sync`, or once with `wrt-sync --candidate`.
- **An older release** of the three kept upgrades like the current one: `sysupgrade /mnt/data/repo/releases/<tag>/targets/*-sysupgrade.tar.gz`. Going back to the other slot needs no upgrade at all: `wrt-slot switch`.

A dev image (`just build dev`) requires signed upgrades as well; it trusts the key its build made. Force a dev image onto a router of your own with `sysupgrade -F`.

## Setting it up

Once, in this order. Each step is the maintainer's; `just github-audit` reads back what GitHub holds.

1. **GitHub.** The `release-signing` environment with the maintainer as required reviewer and `main` and `bump/*` as its only deployment branches; a ruleset on main that requires the checks `check` and `upgrade-drill` (administrators may bypass it).
2. **The release keys**, on the maintainer's own machine:

   ```sh
   just release-keys ~/wrt-release-keys --upload
   ```

   It makes the apk key (EC P-256) and the firmware key (usign) in that new directory, puts their public halves into `feed/utils/wrt-keyring/files`, and with `--upload` stores the private halves as the environment's secrets `RELEASE_APK_KEY` and `RELEASE_FW_KEY`. Back the directory up offline, then delete it; commit the public keys.
3. **Signing on.** The repository variable `RELEASE_SIGNING` set to `enabled` (Settings, Secrets and variables, Actions, Variables). Until then `sign` and what follows are skipped.
4. **The first stable release** is the first run of main after that: approve it, and it is drilled from this build and published.

### Rotating a key

1. Make the new pair with `just release-keys` (without `--upload`); keep both public keys in `wrt-keyring` and publish a release signed with the old key: routers now trust both.
2. Once the routers run it, upload the new private keys (`gh secret set RELEASE_APK_KEY --env release-signing` and the same for `RELEASE_FW_KEY`). The next release is signed with the new keys.
3. When no router needs the old key, remove its public half from `wrt-keyring`.
