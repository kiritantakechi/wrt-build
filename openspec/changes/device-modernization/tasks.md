# Tasks

## 1. Trust anchors in `/etc/usign/keys` (design D5)

- [ ] 1.1 Patch base-files' `fwtool.sh`: it reads `/etc/usign/keys`, or `/etc/opkg/keys` when the new directory does not exist. The patch takes the next free number, its trailer says `Upstream-Status: Pending`, and its write-up goes into `docs/patches.md`.

  Verify: `just patch` applies it. The firmware/ab-upgrade tests pass on both boards: a signed upgrade is taken, and an unsigned one is refused.
- [ ] 1.2 Move every other user of the directory to `/etc/usign/keys`:
  - wrt-keyring, wrt-sync and `files/lib/upgrade/wrt-release.sh`;
  - `scripts/release-keys.sh` and `scripts/release-sign.sh`;
  - the tests' keyring (`tests/wrt_tests/keys.py`);
  - `docs/release-flow.md` and `docs/ops.md`.

  Extend the firmware/base-system test "Check installed packages and executables" to require that there is no `/etc/opkg`.

  Verify: the release suites (signing, device-sync, publishing) pass on both boards. The base-system test passes, and fails on a copy of the image's root that has an `/etc/opkg`.

## 2. The A/B tools in ucode (design D1)

- [ ] 2.1 Add the module `/usr/share/ucode/wrt/ab.uc`: `slot()`, `other()`, `getenv()` and `setenv()`, the last in one `fw_setenv -s -` followed by a sync. Rewrite `wrt-slot` in ucode on it. wrt-ab depends on `ucode` and the modules it uses instead of `jsonfilter`.

  Verify: every function is first tried with the host ucode (`staging_dir/hostpkg/bin/ucode`), and the firmware/health-check scenario "Query status" passes on both boards.
- [ ] 2.2 Rewrite `wrt-healthcheck` in ucode on the module:
  - the built-in checks through ubus and `/proc/net/tcp{,6}`;
  - the limits from uci;
  - the registered checks under `timeout`;
  - the JSON result written natively.

  Verify: all firmware/health-check tests pass on both boards (built-in checks, registered checks and their timeout, trial-boot pass and fail, failure on a confirmed slot), and so do the firmware/boot-rollback tests.
- [ ] 2.3 Keep `/lib/functions/wrt-ab.sh` for the sysupgrade hook alone. Trim it to what the hook uses, and make it and the ucode module each name the other in a comment.

  Verify: the firmware/ab-upgrade tests pass on both boards, and nothing but `lib/upgrade/wrt-ab.sh` sources the shell library.

## 3. wrt-sync's fetch and config-push's device side in ucode (design D2, D3)

- [ ] 3.1 Rewrite wrt-sync's `fetch` in ucode with `ucode-mod-uclient`, with the same retries, channels and outputs. wrt-sync depends on `ucode-mod-uclient` instead of `jsonfilter` and `uclient-fetch`.

  Verify: the release/device-sync tests pass on both boards, including "Release with several boards" and "File that does not match the manifest".
- [ ] 3.2 Replace `scripts/config-push.d/device.sh` with `device.uc`, which `scripts/config-push.sh` runs as `ssh … ucode - <command>`. It has the same commands, messages and rollback, and reads the LAN's state through the ubus module.

  Verify: the ops/config-push tests pass on both boards.

## 4. qosify on tcx (design D4)

- [ ] 4.1 Write the qosify patch:
  - the classifiers attach with `bpf_program__attach_tcx` and `BPF_F_AFTER`, as links the daemon owns;
  - DNS learning reads replies from a packet socket on each managed WAN device, filtered to source port 53, and no longer creates `ifb-dns` and its filters; it receives through `qosify_dns_socket_cb()`, with the IP header aligned (patch 0032);
  - ingress shaping redirects with `bpf_redirect()` to the interface's ifb, whose index the daemon keeps in a map entry per interface;
  - patch 0010's re-attach on a replaced device carries over to the links;
  - a kernel that refuses a tcx link, or `qosify.global.tcx=off`, gets today's `cls_bpf` under `clsact`, after einat's.

  Carry the patch in the series under the next free number, with the trailer `Upstream-Status: Pending` and its write-up in `docs/patches.md`.

  Verify: qosify builds for both boards, with no UB-indicative warning that `tests/reviewed-warnings.toml` does not review, and `tests/build/test_upstream_pinning.py` passes.
- [ ] 4.2 Update and add the tests:
  - network/tc-hook-order "Check the WAN port": tcx ingress and egress hold einat's program, then qosify's, and no legacy filter;
  - "After restarting components" stays as it is;
  - network/qos "Inspect queueing disciplines": no ifb device;
  - "Classify by DNS name" (new): a `dns:` rule to the voice class, a name resolved through the router from a LAN client, and a flow to the address it got;
  - "Enable ingress shaping" (new): cake on the interface's ifb counts a download while it is enabled, and the ifb is gone after the restore.
  - network/tc-hook-order "Kernel without tcx" (new): with `qosify.global.tcx=off`, einat's tcx programs run first and qosify's classifiers on `clsact` after them, and a `dns:` rule still classifies.

  Verify: the network suites pass on both boards. The board-model redial stress, with every CPU of the VM kept busy, keeps einat and qosify on pppoe-wan for eight rounds.

## 5. The code-standards check (design D6)

- [ ] 5.1 Extend the forbidden-pattern check of `scripts/check.sh` over the device code: the feed packages' `files/`, `files/` and `scripts/config-push.d/`. It fails on `jsonfilter`, on sourcing `jshn.sh`, and on `/etc/opkg`, naming the file and the line. Add the test for the quality/code-standards scenario "jsonfilter in a device script".

  Verify: `just check` passes, and the test, which runs the check on a copy of the repository with one offending line, sees it fail with that file and line.

## 6. Integration

- [ ] 6.0 Remove what the change replaced: `git grep` finds no `jsonfilter`, `jshn`, `ifb-dns`, `uclient-fetch` or `/etc/opkg` in this project's device code, scripts, tests or docs, except `fwtool`'s fallback in the base-files patch and the docs that explain it.

  Verify: the code-standards check of task 5.1 passes, and the grep finds only those.

- [ ] 6.1 Run the full system tests on both boards (dev profile).

  Verify: all tests pass on both boards, and `spec-coverage --change device-modernization` reports no uncovered scenario.
- [ ] 6.2 Get a green CI run for both boards.

  Verify: record the run and its per-board timings in `docs/ci.md`.
