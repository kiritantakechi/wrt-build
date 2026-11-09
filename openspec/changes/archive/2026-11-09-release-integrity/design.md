# Design

## Context

See proposal.md for why. The pieces involved:
- `build.yml`: `host-toolchain` → `firmware` (per board) → `caches`, `system-test` → `sign` (environment `release-signing`, main and `bump/*`, not for pull requests) → `drill` → `upgrade-drill` (the required check) → `publish`. One concurrency group per ref, `cancel-in-progress: true`.
- `release-sign.sh` verifies the build's files against its manifest, copies the build (`cp -a build/.`), signs and writes the manifest anew. `release-publish.sh` assembles every board's signed build, checks that they come from the same sources, and creates the release with `gh release create`.
- `bump.yml` pushes `bump/<date>`, opens the pull request with the workflow's token, then dispatches `check` and `build`. GitHub refuses the pull request while the repository does not let workflows create them, and the dispatches never run.
- `cache-room.sh` decides per job whether a cache fits next to the repository's caches; `cache-prune.sh` keeps a ref's newest caches and, on main, deletes merged or deleted branches' caches.
- OpenWrt packs a package into the output directory (`BINARY_FOLDER`, one per board and profile here) when its apk is missing there, older than its build or older than `include/package-pack.mk`, and removes the package's earlier apks as it does (`scripts/ipkg-remove`). A package the configuration no longer selects keeps its apks: the clean rule OpenWrt defines for a deselected package would remove them, and nothing runs it. The package index lists every apk it finds. The kernel's package is the one that is in neither `.config` nor `tmp/.packageinfo` (`package/kernel/linux/Makefile` sets its symbol, out of `DUMP`).
- OpenWrt rewrites a package's compile log whenever it runs the package's compile step: also when it finds it up to date (make's time line alone) and when it only packs it again (the packing's lines, `rstrip.sh` among them, and no compiler output). The build's time log (`BUILD_TIME_LOG`) has a compile stage for a package only when its Build/Compile ran.

## Goals / Non-Goals

**Goals:**
- Every finding of the proposal fixed in the script or workflow where it lies, each with a test that fails without its fix where a unit or static test can reach it.

**Non-Goals:**
- Covering `repo.tar` with the signed manifest: it is assembled at publish time. The router accepts only what the manifest and the signed indexes cover (device-integrity D3).
- Keeping a branch's copy of main's toolchain for a re-run of its firmware jobs after main moved on. Such a re-run fails on the missing cache; a run of the whole workflow builds or restores the toolchain again. A copy per branch would double the toolchain's 0.8 GB in the quota.
- Requiring approval for every outside contributor's pull request. That is a repository setting and the maintainer's call; `docs/ci.md` names it.

## Decisions

### D1. Publish what was built, from where it still stands

- `build.sh` records this repository's commit in the manifest (`commit`), with `-dirty` appended when tracked files differ from it.
- `release-publish.sh` requires every board's manifest to name the same commit, and the checkout's `upstream.lock` to hash as the manifests say.
- With `--upload`, it refuses a `-dirty` commit, and refuses a commit that is not the head of the branch it publishes from (`GITHUB_REF`, read back with `gh api`). It then creates the release with `--target <commit>`.
- `build.yml`'s concurrency group cancels in-progress runs only for a run's first attempt (`cancel-in-progress: ${{ github.run_attempt == '1' }}`). A re-run waits for the newer run, and its publish then fails the head check.

### D2. Signing takes the build by its artifact's name, and only what its manifest lists

- `build.sh`'s manifest lists every file the build hands on, the packages included, which until now only the signed indexes covered: what signing passes on is then what the manifest lists.
- The `sign` job takes each board from its artifact's directory name (`firmware-unsigned-<board>`), refuses one that is not a board of `boards/`, and refuses a manifest whose `board` is another.
- A new library module, `scripts/lib/manifest.sh`, holds the check of a manifest's files and the checksum lines of a selection of them; `build.sh`, `release-sign.sh`, `release-publish.sh` and `drill-base.sh` use both. The check refuses any file name that is not a plain relative path: no leading `/`, no empty, `.` or `..` component, nothing but `[A-Za-z0-9._+~-]` between the slashes (`~` is apk's separator of a snapshot's version), and any value that is not a sha256. jq's `^` and `$` would let a final line break through, so it anchors with `\A` and `\z`.
- `release-sign.sh` checks the checksums with `--strict`, and copies the files the manifest lists, nothing else, then writes the manifest anew.
- `release-publish.sh` and `drill-base.sh` check with `--strict` too. `build.sh` refuses an output file whose name `sha256sum` would escape.

### D3. One pinned installer

`.github/actions/nix/action.yml`, a composite action, runs `DeterminateSystems/nix-installer-action@v23` with `source-tag: v3.23.3`, the installer of the last green run. Every job uses it after its checkout. A newer installer is a change of that one line.

### D4. The drill check of a bump's pull request

`upgrade-drill` fails when the run is a pull request's from a `bump/` branch while `RELEASE_SIGNING` is `enabled`. Its message names the branch's own run (`gh workflow run build.yml --ref <branch>`), which signs and drills. Other pull requests keep passing on their system tests, as no other pull request publishes.

### D5. The bump: checks first, its branch never overwritten

- A branch that exists stays as it is: the bump may carry the maintainer's commits.
- A new branch is pushed, then `check` and `build` are dispatched on it, then the pull request is opened.
- A run on a day whose branch exists opens the pull request it lacks, if there was never one.
- A pull request that cannot be opened fails the step with the setting to change.
- `github-audit.sh` reads `actions/permissions/workflow` and fails when `can_approve_pull_request_reviews` is false. That setting also lets workflows create pull requests. When the token cannot read it, as a workflow's cannot (it needs administration access), it reports that instead of failing.

### D6. Caches

- **Download cache:** the firmware job downloads in a step of its own, a new entry point (`just download`, `scripts/download.sh`: `make download` in the FHS environment, as `build.sh` runs it too). The download cache is saved only when that step succeeded.
- **Room:** `cache-room.sh` multiplies the paths' size by `CACHE_SAVERS`, the number of jobs that save at once. Each firmware job asks once, for its download and compiler caches together, with `strategy.job-total`: a check of one cache alone would miss the other kind that another board's job saves meanwhile. The download cache, whose key the boards share, then counts more than once, which errs on the side of main's caches.
- **Pruning:** `cache-prune.sh` takes a compiler cache's stage as its key without the trailing settings hash and run ID, so a hyphen in a stage's name is no field separator. On main it also deletes the caches of `refs/pull/<n>/merge` whose pull request is closed.
- **Toolchain key:** `toolchain-key.sh` adds the makefiles of the target and subtarget the board-neutral configuration selects (`target/linux/<target>/Makefile`, `target/linux/<target>/<subtarget>/target.mk`). They name what the toolchain is built for: the architecture, the CPU type, the features and the kernel version (`KERNEL_PATCHVER`), whose headers the toolchain carries. The devices are defined in the target's `image/` files, so a new device keeps the key; a change of the target's default packages moves it, a rare rebuild in exchange for not picking the toolchain's inputs out of the makefiles' lines one by one.

### D7. Triggers and concurrency

- `build.yml` triggers on `paths: ["**", "!openspec/**", "!docs/**", "!**/*.md", <the documents tests read>]`. A unit test finds the documents the tests read (`"docs" / "<name>"`) and requires each in the list, and the list to hold no other.
- `check.yml`'s group includes the event's name, so a scheduled run and a push run never share one.

### D8. Host scripts

- **The `justfile`** sets `positional-arguments`. Every recipe that takes arguments runs its script with `"$@"`, never `{{ }}`.
- **`series_commit` and `move_tree`** run git with `GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_NOSYSTEM=1`. Fetching keeps the user's configuration (proxies, mirrors).
- **`build.sh`'s UBSan check** first runs `nm --version` and dies when that fails.
- **`marks-check.sh`** dies when grep reports an error, its status 2.
- **`toolchain-pack.sh`** makes a relative archive path absolute before it changes directory, as `toolchain-unpack.sh` reads it.

- **`build.sh`** removes, before `make`, the apks of the board's output directory whose package the configuration does not build (`stale_packages`, `tree.sh`): a package builds when `.config` selects it (`=y` or `=m`), and its apk is named after it with its ABI version from `tmp/.packageinfo`. make's package index then lists this build's packages. Emptying the directory instead, as upstream's builders do, would have every package packed again, and its warnings forgotten (next point).
- **`warnings_harvest`** takes the packages to record from the build's time log, those with a compile stage, instead of every log written since the build began that holds more than make's time line. A compiled package's log has its compiler output, and one that compiles without a word gets an empty record as before. Upstream's time log named a host build's stages as the target build's, by the package's directory: a host build of a package whose target build only packed again would have had its target log read. Patch 0042 names them host-prepare, host-configure, host-compile and host-install, as the host build's make targets and logs are named; it also keeps the begin and end of a host and a target stage that run at once from pairing with each other's in upstream's report. The toolchain key covers `include/host-build.mk`, so the first CI run with the patch builds the host toolchain anew.

### D9. Tests

- Static, of the workflows (`tests/build/test_ci.py`):
  - every job installs Nix through the local action, which pins `source-tag`;
  - build's concurrency cancels in-progress runs only for a run's first attempt;
  - the paths filter lists exactly the documents tests read;
  - check's group holds the event's name;
  - bump dispatches before it opens the pull request, and never pushes over an existing branch;
  - `upgrade-drill` fails for a bump's pull request.
- Of the scripts, against stand-ins:
  - `cache-prune.sh` with hyphenated stages and a closed pull request's caches (`tests/unit/test_ci_caches.py`);
  - `cache-room.sh` with several savers;
  - `release-sign.sh` refusing a path out of the build and passing on only listed files (`tests/release/test_signing.py`);
  - `release-publish.sh` refusing another lock or commit, and the target and head check with a stand-in `gh` (`tests/release/test_publishing.py`);
  - `series_commit` under a global configuration with `apply.whitespace=fix` and `commit.gpgSign` (`tests/build/test_upstream_pinning.py`);
  - a `just` recipe given an argument with a blank and a `;`.
- `stale_packages` on a stand-in output directory and configuration (`tests/unit/test_lib.py`); `warnings_harvest` on stand-in logs and a time log, for quality/undefined-behavior's "Package packed again without a compile" (`tests/quality/test_undefined_behavior.py`).
- The toolchain key: on the VM, a changed `KERNEL_PATCHVER` line changes the key, and a new device in the target's `image/` files does not; recorded in `tests/verified-elsewhere.toml`.

## Risks / Trade-offs

- [A re-run that waits behind a long run] → It waits for the newer run, which was going to publish anyway; the re-run's publish then fails the head check, by design.
- [`can_approve_pull_request_reviews` unreadable in CI] → The weekly audit says so; `just github-audit` with the maintainer's token reads it.
- [The installer pinned] → A security fix in a newer installer needs the one-line change; `docs/ci.md` says where.
