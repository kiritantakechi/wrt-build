# honk: review of the forks and the build's dependencies

Reviewed: 2026-11-13 (honk-datapath task 9.1). honk v0.1.0-beta.6 takes four crates from the git repositories of one owner, `Glassyiris`, who is honk's principal author: boring-sys (its BoringSSL bindings) from `Glassyiris/boring-sys`, and quinn, quinn-proto and quinn-udp (its QUIC stack) from `Glassyiris/quinn`. The review also covers the crates honk's lockfiles pin, doona (the web UI honk embeds) with its npm dependencies, and bpf-linker, the host tool that links honk's eBPF object.

Subject: honk v0.1.0-beta.6, tag `v0.1.0-beta.6` (annotated, signed by Zakkaus; GitHub reports the signature valid), commit `64848881b7304e250e7a25422f4f1d86a5975eca`, the version `feed/net/honk/Makefile` packages (`honk-0.1.0-beta.6.tar.gz`, sha256 `cfddedeafa349d0bdfaebd792d6f15c9f31de46a051e5a0692749a74f69d8e6d`). The recipe builds `crates/honk-core` with `--no-default-features` and the features `ebpf,native-ui,jemalloc,rprx`; its patches (`feed/net/honk/patches`) change honk-core's build script and add a command, and touch no dependency.

## What the build takes

| Input | Source | Pin |
|---|---|---|
| honk | `daeuniverse/honk`, tag archive | commit `64848881b730`, `PKG_HASH` above |
| honk-core's crates | crates.io, honk's `Cargo.lock` | 456 crates, a sha256 each |
| boring-sys 5.2.0 | `Glassyiris/boring-sys`, git | rev `3beb573b65ecaa69b7eefe3c2fecd074b97facd2` |
| quinn 0.11.12, quinn-proto 0.11.19, quinn-udp 0.5.16 | `Glassyiris/quinn`, git | rev `11f1de84c28305a3c98ace6d681c35219a8d1e6c` |
| honk-ebpf's crates | crates.io, `crates/honk-ebpf/Cargo.lock` | 61 crates, a sha256 each |
| doona 0.1.0-rc.6 | `Zakkaus/doona`, tag archive | commit `4c1f6f3fc152`, `PKG_HASH` below |
| pnpm 11.15.1 | registry.npmjs.org | `HASH` below |
| doona's npm packages | two pnpm lockfiles | 558 and 217 packages, a sha512 each |
| bpf-linker 0.11.0 | `aya-rs/bpf-linker`, tag archive (not the crates.io package) | commit `a85291e0d611`, `PKG_HASH` below |
| bpf-linker's crates | its `Cargo.lock` | 134 crates, a sha256 each; one git dev-dependency |

## Pinned versions

honk names crates.io versions in `[workspace.dependencies]` and swaps in the forks with `[patch.crates-io]` ([Cargo.toml](https://github.com/daeuniverse/honk/blob/64848881b7304e250e7a25422f4f1d86a5975eca/Cargo.toml)):

| Item | Value |
|---|---|
| `[workspace.dependencies]` (L79–81, L105–106) | `boring = "=5.2.0"` (feature `mlkem`), `boring-sys = "=5.2.0"`, `tokio-boring = "=5.2.0"`, `quinn = "0.11"`, `quinn-proto = "0.11"` |
| `[patch.crates-io]` (L182) | `boring-sys = { git = "https://github.com/Glassyiris/boring-sys", rev = "3beb573b65ecaa69b7eefe3c2fecd074b97facd2" }` |
| `[patch.crates-io]` (L186–187) | `quinn` and `quinn-proto` = `{ git = "https://github.com/Glassyiris/quinn", rev = "11f1de84c28305a3c98ace6d681c35219a8d1e6c" }` |

Cargo.lock (L521–523, L2788–2790, L2808–2810, L2832–2834):

```
boring-sys 5.2.0     git+https://github.com/Glassyiris/boring-sys?rev=3beb573b65ecaa69b7eefe3c2fecd074b97facd2#3beb573b65ecaa69b7eefe3c2fecd074b97facd2
quinn 0.11.12        git+https://github.com/Glassyiris/quinn?rev=11f1de84c28305a3c98ace6d681c35219a8d1e6c#11f1de84c28305a3c98ace6d681c35219a8d1e6c
quinn-proto 0.11.19  (the same source)
quinn-udp 0.5.16     (the same source)
```

Verification:
- **Every crates.io package carries a checksum.** Cargo.lock (version 4) lists 466 packages: 456 from crates.io, each with a sha256 `checksum`, 4 from git, and the 6 workspace crates. OpenWrt's `rust-package.mk` builds honk-core with `cargo install --locked` (`RUST_PKG_LOCKED` defaults to 1), so Cargo refuses a lockfile change and checks every crate it downloads against its checksum. `cargo vendor --locked` of the whole lockfile succeeded, which checked all 456 against the files crates.io serves.
- **The git packages are pinned by full commit only.** Cargo records no checksum for a git package: the commit id is the pin. A force-push cannot change what is built; a deleted branch or repository can make the commit unfetchable. Cargo keeps its git checkouts in `CARGO_HOME`, which OpenWrt sets to `$(DL_DIR)/cargo`.
- **quinn-udp comes from the fork although `[patch]` does not name it:** quinn depends on it by path inside the fork's workspace. The fork's crates carry the version numbers of upstream's latest releases (quinn 0.11.12, quinn-proto 0.11.19, quinn-udp 0.5.16), while their code is newer than those releases and modified: the versions do not identify the content.
- **`[patch]` replaces boring-sys in the whole graph,** whatever the features: the patched BoringSSL is linked even without `rprx`.
- **What the firmware links.** `cargo tree --locked -e normal,build` with the recipe's features gives the same 316 packages for `aarch64-unknown-linux-musl` and `x86_64-unknown-linux-musl`: the 5 workspace crates honk-core uses, 307 crates from crates.io and all 4 git packages.
- **Default features dropped.** honk-core's defaults are `clash-api`, `jemalloc` and `rprx`. The recipe drops `clash-api` (D8): no Clash REST API and no external-UI download (`zip` is not in the firmware set). It keeps `jemalloc` and `rprx` (the VLESS and VMess handlers with REALITY, the only user of the boring-sys hooks), and adds `ebpf` and `native-ui` (the native API, with axum, and the embedded doona).
- **honk-ebpf** is outside the workspace and has its own Cargo.lock: 63 packages, 61 from crates.io with checksums, 2 path crates, no git. The recipe builds it with `cargo build --locked -Zbuild-std=core`, which also compiles `core` from the `rust-src` of the build's Rust 1.99.1.

## The boring-sys fork

| Item | Value |
|---|---|
| Repository | https://github.com/Glassyiris/boring-sys, created 2026-08-05; not a GitHub fork ("another for boring-sys"); 7 commits in all |
| Resolved commit | `3beb573b65ecaa69b7eefe3c2fecd074b97facd2` (2026-09-02, "fix(rprx): rebase clienthello fixup hunk onto boringssl 5.2.0"), tip of branch `boring-sys-5.2`; the default branch `master` holds the same work on 5.1.0 |
| Base | `90436a8e9a066b7f9a62aa9364449631a2e6f467`, "boring-sys 5.2.0 baseline (crates.io)" |
| BoringSSL | vendored in `deps/boringssl`, BoringSSL commit `e2a57cfb4d915b4ba820585aef9fdee7bca13fe5` (2026-05-20) |

### Fork point

- **The base is the crates.io package, not a git history.** `90436a8` is byte-identical to the crates.io package boring-sys 5.2.0 (sha256 `6993efa9d9f0ebf3b0c02c8e868cfe37d0854cd021d51204480a91ce23d6e444`, as the crates.io index lists it), apart from Cargo's extraction marker `.cargo-ok`. Its parent `7f7f40e` is likewise the package 5.1.0.
- **That package is cloudflare/boring's v5.2.0.** Its `.cargo_vcs_info.json` names `6fdd0a54e81a1eecc76e587c685439d3f2ffdd09` in https://github.com/cloudflare/boring, the commit of tag `v5.2.0` (2026-06-19).
- **The BoringSSL source matches upstream.** All 1,602 files of `deps/boringssl` (the crate keeps only the file kinds its `include` list names) are byte-identical to BoringSSL commit `e2a57cfb`, the submodule commit cloudflare/boring's v5.2.0 records, fetched from boringssl.googlesource.com. That commit is untagged; it is an ancestor of BoringSSL's tag `0.20261105.0`, so it lies on BoringSSL's main line.
- **The build script fetches nothing.** It runs `git submodule update` only when `deps/boringssl/CMakeLists.txt` is missing, which it is not. It copies the tree to `OUT_DIR`, runs `git init` and `git apply` for its patches, then CMake and bindgen. The package and the fork contain no prebuilt objects.

### Changes

Three commits on the base, 2 files, +217/−0:

| Commit | Author | Content |
|---|---|---|
| `91cf08e` | `agent <agent@local>`, committed by `eries` | adds `patches/rprx-client-hooks.patch` and applies it in `build/main.rs` |
| `b7fa8d9` | `eries <coloredflowers@outlook.com>` | after the fixup callback, re-reads `hs->session_id` from the message |
| `3beb573` | `eries` | moves one hunk header to BoringSSL as 5.2.0 vendors it |

- **`build/main.rs` (+3 lines)** applies the patch after upstream's `boring-pq.patch`, unconditionally: no Cargo feature gates it, so every build from this fork carries the hooks.
- **The patch** (6 BoringSSL files, about 90 added lines) adds two client-side functions:
  - `SSL_set1_client_x25519_private_key(ssl, key)`: the X25519 key share of the first ClientHello uses a caller-supplied private key (`X25519_public_from_private`) instead of a fresh random one (`X25519_keypair`).
  - `SSL_set_client_hello_fixup_cb(ssl, cb)`: a callback that may rewrite the serialized ClientHello in place, after it is complete (binder included) and before it enters the transcript and the wire. Afterwards `hs->session_id` is re-read from the message, so the TLS 1.3 session-id echo check compares the ServerHello against what was sent.
  REALITY needs both: its client hides an authenticated token in `legacy_session_id`, keyed by ECDH between its ephemeral key and the server's REALITY key.
- **The patch applies cleanly** to the vendored BoringSSL after `boring-pq.patch`, with `git apply` as the build script runs it (one hunk at an offset).
- **Authorship and review:** no commit is signed (GitHub: "unsigned"). Three of the seven commits (the 5.1.0 baseline and both versions of the hooks commit) are authored `agent <agent@local>`, an AI tool's identity. GitHub maps `eries <coloredflowers@outlook.com>` to the account `Glassyiris`, which has 896 of the contributions to daeuniverse/honk; honk's `Cargo.toml` names `Glassyiris/honk` as its repository. Nothing of the fork was proposed to cloudflare/boring (no issues or pull requests by that account).

### Security-relevant findings

- **Nothing outside the two client hooks.** No change to crypto primitives, randomness, certificate or X.509 handling, the Rust bindings (`src/lib.rs`), or the build script beyond the one apply line; no endpoints, no binaries, no execution beyond upstream's `git`, CMake and bindgen.
- **The hooks are inert unless called.** The only caller is honk-outbound's REALITY client (`crates/honk-outbound/src/reality.rs`, feature `rprx`, which the firmware enables):
  - the preset key is 32 bytes from BoringSSL's `RAND_bytes`, new for every connection, so forward secrecy is that of a random ephemeral key;
  - the callback seals one ClientHello only (a HelloRetryRequest would reuse the AES-GCM key and nonce), checks the message type and a 32-byte session id, and returns 0 on any failure, which aborts the handshake: no unauthenticated REALITY ClientHello is sent;
  - REALITY turns ordinary certificate verification off (`skip_verify`) and checks instead that the server's Ed25519 leaf signature equals HMAC-SHA512(authKey, its public key) (`verify_server_certificate`). That is REALITY's design, not the fork's.
- **Caveats, read from source:** the callback runs after the PSK binder, so a rewrite invalidates resumption (the patch says so; REALITY does not resume). BoringSSL zeroes the preset key when it frees it (`OPENSSL_free`); honk's own copy of the key and of the auth key (`RealityHandshake`) is freed without zeroing.
- **Stale.** honk pins boring, boring-sys and tokio-boring `=5.2.0`, because the fork patches exactly that version. cloudflare/boring is at 5.5.0 (2026-11-10), with BoringSSL `0.20261020.0`; BoringSSL's `0.20261105.0` is 569 commits past the pinned BoringSSL. BoringSSL publishes no advisories. A scan of those 569 commit subjects for fixes found hardening whose messages call it unreachable (an `SSLBuffer::EnsureCap` overflow guard, a loop index in `pki/`) and a constant-time fix in ML-KEM's test-only key format; none is described as exploitable in a TLS client. This is a subject scan, not a review.
- **One fix in the boring crate after 5.2.0 does not apply:** 5.3.0 made `AeadCtx` sealing take `&mut self`, for the stateful TLS AEADs (quiche#2383). Those constructors do not exist in 5.2.0, and honk uses only the stateless AES-GCM and ChaCha20-Poly1305 contexts.
- **Advisories:** RustSec has none for boring, boring-sys or tokio-boring. cloudflare/boring's one GitHub advisory (CVE-2023-6180) concerns tokio-boring 4.0.0.

## The quinn fork

| Item | Value |
|---|---|
| Repository | https://github.com/Glassyiris/quinn, a GitHub fork of quinn-rs/quinn created 2026-08-31; working branch `honk-0.11`, "upstream 0.11.x + patches" |
| Resolved commit | `11f1de84c28305a3c98ace6d681c35219a8d1e6c` (2026-10-24, "perf(pr-12): raise the BBRv3 loss threshold to 5%"), head of the fork's pull request #12, merged into `honk-0.11` as `26d828b3`, whose tree is identical |
| Merge base with upstream 0.11.x | `98c9372f924003b030222975cc32d5ff53621b34` (2026-10-12, "proto: account for application close error code width"), 27 commits after quinn-proto 0.11.19, quinn-udp 0.5.16 and quinn 0.11.12 (2026-09-30) |
| Ahead / behind | 42 commits ahead (37 plus 5 merges); 11 behind upstream's 0.11.x (`a9ae122f`, 2026-11-09) |

### Fork point and upstream comparison

- **The branch follows upstream 0.11.x by merges:** 2026-10-02, 2026-10-08 (by a `honk-sync` identity) and 2026-10-23 ("Merge upstream 0.11.x (98c9372f) into honk-0.11"). The fork has no tags.
- **Size of the diff** (merge base to pin):

  | Part | Lines added | Lines removed |
  |---|---|---|
  | All (24 files) | 8,700 | 83 |
  | Test directories (`quinn-proto/src/tests`, `fuzz`, `perf`) | 473 | 4 |
  | BBRv3 tests (inside `congestion/bbr3`) | about 5,090 | 0 |
  | Other non-test code | about 3,100, of which about 2,150 the BBRv3 controller | 79 |

  No change touches `Cargo.toml`, `Cargo.lock`, a build script, `quinn-udp`, the crypto modules, transport parameters, packet protection, or the Retry and token code.
- **Authorship:** of the 37 non-merge commits, 31 are the owner's (`eries` 30, `Glassyiris` 1) and 6 are upstream commits cherry-picked from quinn-rs/quinn's `main`. 21 carry a GPG signature (key `6C4E0ACA51303165`; GitHub reports the pin's signature valid); 16 are unsigned, among them the assembler change and the 2026-09-01 flow-control series. Of the 5 merges, two are GitHub web merges of the fork's pull requests #10 and #11, two are signed by `eries`, one is the unsigned `honk-sync` merge.
- **Upstream review:** none of the owner's changes was proposed to quinn-rs/quinn (no pull requests by that account). The BBRv3 controller is "ported from n0-computer/noq f40e4024 … itself synced from quinn-rs/quinn#2481"; #2481 (by Tipuch, opened 2025-12-21) is open and unmerged, and the port differs from that pull request's file in about 1,200 lines of the non-test part. It entered the fork through the fork's own pull request #12, merged by its owner.
- **The cherry-picks match upstream:** "Send CONNECTION_CLOSE even when congestion blocked (#2787)", "Improve numerical stability of Pacer::delay", "Use `saturating_mul` when calculating `congestion_period`", "Reuse one receive buffer per batch" (identical patch ids), "apply RFC 9000 §12.4 packet-type rules to CONNECTION_CLOSE (#2804)" and "fix: update stale waker" (adapted to 0.11's API in test code only).

### Changes

- **Receive assembler limit raised** (`a147057a`, 2026-08-31): `MAX_CHUNKS` from 1,024 to 16,384, "for lossy paths" with 8 MiB windows. Upstream added this limit for RUSTSEC-2026-0185 (GHSA-4w2j-m93h-cj5j) and tightened it for RUSTSEC-2026-0341 (GHSA-qfwj-vfxf-92j2): the number of separate out-of-order chunks one receive stream may buffer before the connection is closed, with compaction at twice that.
- **Flow control at run time:** `Connection::set_stream_receive_window`, and `TransportConfig::receive_window_autotune`, which doubles the connection receive window up to a cap whenever the application reads more than half of it within four round trips times the fraction read; the window never shrinks, and a reader that stalls does not grow it. honk enables it whenever a node sets a connection receive window, with a cap of at least 32 MiB, and moves stream windows between 8 and 32 MiB (`crates/honk-outbound/src/quic/flow_control.rs`).
- **Statistics:** delivered, acknowledged and flow-control counters (`FlowControlStats`, ack-eliciting packet counts).
- **Congestion-control interface:** per-packet events (`on_packet_sent`, `on_packet_acked`, `on_packet_lost`, ECN, congestion-window-limited), a pacing rate and send quantum set by the controller (`ControllerMetrics::pacer_rate`, `send_quantum`), `SpaceId` exported and `#[non_exhaustive]`.
- **BBRv3** (`quinn-proto/src/congestion/bbr3`): `rand` and `rand_pcg`, both existing quinn-proto dependencies, randomize its probing; no security use. honk uses it for every QUIC node whose congestion control is `bbr`, which includes Hysteria2 nodes without an upload rate, unless `HONK_QUIC_BBR=v1` selects quinn's original BBR. honk's DNS over QUIC and over HTTP/3 use cubic.
- **Endpoint driver I/O errors** are logged at debug instead of error ("honk retires probe/warm endpoints this way routinely").

### Security-relevant findings

- **Nothing of the kinds searched for:** the added non-test lines have no URLs other than documentation links, no `unsafe`, FFI, `std::process`, `std::env`, file access, `include_bytes`, new dependencies or build-script changes.
- **The crypto path is not the fork's.** honk's QUIC clients, the DoQ and DoH3 resolvers included, use BoringSSL through honk's own adapter (`crates/honk-outbound/src/quic/boring.rs`, `impl crypto::ClientConfig`). quinn's default features still compile its rustls and ring path.
- **A peer can cost more memory:** a QUIC peer can make honk buffer up to 16,384 out-of-order chunks per stream (compaction at 32,768) before honk closes the connection, 16 times upstream's bound, and the connection receive window can grow to honk's cap (at least 32 MiB). The bound still holds. honk only dials QUIC (no QUIC server in its non-test code), so the peers are configured proxy nodes and DoQ or DoH3 servers.
- **The new frame handling opens no stream:** a peer's STREAM_DATA_BLOCKED now has its stream id validated (unopened and over-limit ids close the connection) and can queue MAX_STREAM_DATA for an existing stream only, so the class of GHSA-53rm-773f-4q8c ("MAX_STREAM_DATA frame opens streams over the stream limit") is not reopened. Read from source.
- **Advisories:** all eleven RustSec advisories for quinn and quinn-proto and quinn-rs/quinn's three GitHub advisories of 2026-09-30 (GHSA-53rm-773f-4q8c, GHSA-wppq-2f6r-wfvm, GHSA-6pp4-4cxf-xf88 in quinn-udp) are fixed in releases that are ancestors of the merge base, and the fork reverts none of the fixes; it relaxes the constant above. **Scanners see only the version:** cargo-audit and OSV take the fork's crates for quinn-proto 0.11.19 and quinn-udp 0.5.16 and will report advisories against those versions, whether or not the fork carries a later fix.
- **Stale:** the 11 upstream 0.11.x commits the fork lacks have no advisory as of 2026-11-13; they include "proto: discard incoming 0-RTT packets as client", "proto: don't credit a reset stream's unread data twice on stop", "proto: don't send MTU probes on an unvalidated path" and "quinn: release socket on connection driver drop".
- **No drop-in upstream:** honk calls APIs only the fork has (`receive_window_autotune`, `set_stream_receive_window`, `Bbr3Config`, `pacer_rate`, the flow-control statistics).

## The crates

- **Known advisories.** The RustSec database (rustsec/advisory-db at `af7b3ec3`, 2026-11-12), matched by version against all 460 non-path packages of honk's Cargo.lock, and OSV's batch query give the same three:

  | Advisory | Crate | Kind | In the firmware |
  |---|---|---|---|
  | RUSTSEC-2024-0449 | unsafe-libyaml 0.2.11 | unmaintained | yes, through serde_yaml 0.9.34+deprecated, which parses honk's configuration and the subscriptions fetched from their URLs |
  | RUSTSEC-2025-0134 | rustls-pemfile 2.2.0 | unmaintained | no (tests) |
  | RUSTSEC-2026-0486 | rustix 1.1.5 | unsound (xattr functions) | no |

  honk-ebpf's 61 crates match nothing. Neither "unmaintained" entry reports a vulnerability; unsafe-libyaml is a translation of libyaml with `unsafe` code, here parsing input from subscription providers.
- **Build scripts.** 41 crates of the firmware set have one. None downloads anything or uses an HTTP client (their URLs are in comments and error messages); they run the C compiler, CMake (BoringSSL, AWS-LC), `sh` and `make` (jemalloc's configure), `git` (boring-sys's patches) and `rustc -vV`. honk-core's own build script runs `git` for its version, embeds doona from `HONK_DOONA_DIR` and, with patch 001, the prebuilt eBPF object.
- **Prebuilt objects:** only for Windows targets (ring's `pregenerated/*nasm*.o` and `*win32n.o`, aws-lc-sys's `builder/prebuilt-nasm`, which it uses only on `windows` x86_64), and winapi's import libraries, which are not in the firmware set.
- **Native code built from source into the binary:** BoringSSL (the fork), AWS-LC (aws-lc-sys 0.46.0, the rustls provider reqwest's `rustls` feature selects, used by honk-core's HTTP client for subscriptions and geodata), ring 0.17.14 (rustls-webpki, quinn's rustls path), SQLite (libsqlite3-sys, bundled) and jemalloc (tikv-jemalloc-sys).
- **Licences.** Read from the `license` field of each vendored crate (`cargo vendor --locked`). The firmware set's 311 external crates are MIT, Apache-2.0 or both (261), Unicode-3.0 (18), BSD-3-Clause, ISC, Zlib, Unlicense, 0BSD, CC0-1.0/MIT-0 or BSL-1.0 as alternatives, `Apache-2.0 AND ISC` (ring), a conjunction of ISC, Apache-2.0, MIT and BSD-3-Clause terms (aws-lc-sys; its OpenSSL-derived files are Apache-2.0 under its LICENSE) and CDLA-Permissive-2.0 (webpki-root-certs: Mozilla's CA certificates as data). The bundled C carries Apache-2.0 (BoringSSL's LICENSE), jemalloc's BSD-style licence and SQLite's public-domain dedication. All are compatible with honk's GPL-3.0-only; CDLA-Permissive-2.0 is a permissive data licence that is not on the FSF's list. Outside the firmware set the lockfile adds only permissive licences and two `MIT OR Apache-2.0 OR LGPL-2.1-or-later` choices.

## doona

| Item | Value |
|---|---|
| Source | `Zakkaus/doona`, tag `v0.1.0-rc.6` (annotated, signed by Zakkaus; GitHub reports the signature valid), commit `4c1f6f3fc1523558d595c363ba677494844030e3` (unsigned), GPL-3.0-only |
| Archive | `doona-0.1.0-rc.6.tar.gz`, sha256 `d8b85ac93d692e507ce1174a8a1f23be3d2f7ff6a413ce43be061d9088d9b6f6` (`PKG_HASH`) |
| honk's own pin | `.github/ci/pins.env`: `DOONA_VERSION=0.1.0-rc.6`, `DOONA_REVISION=4c1f6f3fc1523558d595c363ba677494844030e3` |
| pnpm | 11.15.1 (doona's `packageManager`), `pnpm-11.15.1.tgz` sha256 `27460629b10111604e7f98882753b53398986820c20e0a065f3a4a5e9e7db71f` (`HASH`); its sha512 equals the registry's `dist.integrity` |

- **Two independent lockfiles** (pnpm lockfile 9.0): `pnpm-lock.yaml` (558 packages, importer `.` only) and `apps/lite/pnpm-lock.yaml` (217 packages); `apps/lite` has its own `pnpm-workspace.yaml` and is not part of the root workspace. Every package resolves from the npm registry with a sha512 `integrity`; there are no tarball URLs, git or directory sources. 86 and 27 of the packages are platform-specific (native binaries, mostly); only the build host's are installed.
- **The lite edition's dependencies are installed implicitly.** The recipe runs `pnpm install --frozen-lockfile` at the root only. pnpm 11.15.1 defaults `verify-deps-before-run` to `install`, so `pnpm -C apps/lite build` installs `apps/lite` first, and with `CI=true` that install uses the lockfile frozen (`frozenLockfileIfExists`). doona's release workflow runs `pnpm -C apps/lite install --frozen-lockfile` explicitly. Read from pnpm's source, not observed in the recipe's build.
- **The recipe's store setting has no effect.** pnpm 11 takes its settings from `pnpm_config_*` variables and ignores `npm_config_store_dir`. With the recipe's variables the store landed in `$XDG_DATA_HOME/pnpm/store/v11`, which the recipe places in the build directory, not in `$(DL_DIR)/pnpm-store`: each clean build downloads every tarball again (still integrity-checked). Observed in an install on macOS with the recipe's variables.
- **Install scripts.** pnpm 11 runs a dependency's lifecycle scripts only if `allowBuilds` allows it, and fails an install with an unlisted one (`strict-dep-builds` defaults to true). doona allows `esbuild` and denies `unrs-resolver`; `apps/lite` allows `esbuild` (not in its lockfile) and denies `@astryxdesign/core` and `@astryxdesign/cli`. An install with `--ignore-scripts` (472 and 193 packages on darwin/arm64) found `preinstall`, `install` or `postinstall` scripts in exactly those four: esbuild 0.25.12 (`node install.js`, the one that runs), unrs-resolver 1.12.2, and @astryxdesign/core and cli 0.6.8. Other packages declare only `prepare`, which an install from the registry does not run.
- **Fetched outside the lockfile at build time:**
  - pnpm 11 defaults `minimum-release-age` to 1,440 minutes and checks every lockfile entry against it before installing, fetching each package's metadata from registry.npmjs.org. A build therefore needs the registry even with a full store; it refuses packages younger than a day.
  - esbuild's `install.js` checks the platform package the lockfile installed (`@esbuild/linux-arm64` and so on); only if it is missing does it fall back to `npm install` or a download from registry.npmjs.org.
  - If `PNPM_VERSION` differs from doona's `packageManager`, pnpm 11 switches to the named version, downloading it (signature-checked, not hash-pinned by the recipe).
- **Prebuilt binaries run on the build host:** esbuild, rollup (doona) or rolldown (lite), lightningcss and pnpm's own bundled native modules come from npm as binaries, pinned by integrity, not built from source.
- **What the build does:** `pnpm build` and `pnpm -C apps/lite build` run `vite build` with React, React Aria's locale plugin, astryx's StyleX plugin (lite) and doona's own Vite plugins in `tools/`; `tools/package.sh` precompresses with brotli and gzip, adds the licence notices (`tools/notices.mjs`) and writes archives with `SOURCE_DATE_EPOCH`. The Vite configurations and doona's build plugins contain no URL and start no process (only test scripts do); `package.sh` runs node, brotli, gzip and tar on local files. The recipe drops each edition's `fonts/`.
- **The UI itself** requests only paths relative to its origin (honk's native API) and links to daeuniverse.org's manual and the GitHub issue tracker; a search of `src/` and `apps/lite/src/` found no request to another host.
- **Advisories** (`pnpm audit` against the npm registry, 2026-11-13): the lite lockfile has none. The root lockfile has 14 (3 high, 8 moderate, 3 low) in six packages: vite 6.4.3 (5, its dev server and editor launcher), @vitest/mocker 5.0.2 (2), source-map-js 1.2.1 (1, denial of service on crafted source maps), zod 4.6.5 (1), fast-uri 3.1.8 (4) and minimatch 10.2.6 (1). Every path starts at a devDependency (vite, vitest, eslint and its plugins, stylelint, ajv), none at one of doona's 16 runtime dependencies, so none of these packages is in the bundle honk embeds. The build runs `vite build`, not the dev server; source-map-js reads doona's own source maps.
- **Licences of the shipped code** (`pnpm licenses list --prod`): 36 runtime packages for doona (MIT 23, Apache-2.0 8, ISC 2, 0BSD 1, OFL-1.1 2, the fonts) and 34 for lite (MIT 29, ISC 2, BSD-3-Clause 1, `BSD` 1 for css-mediaquery, OFL-1.1 1, a font), all compatible with GPL-3.0-only. The development tools' licences were not surveyed; they do not ship.

## bpf-linker

| Item | Value |
|---|---|
| Source | `aya-rs/bpf-linker`, tag `v0.11.0` (lightweight), commit `a85291e0d6112ec86e0331b68779ba07f7a5a1e9` (unsigned), MIT OR Apache-2.0 |
| Archive | `bpf-linker-0.11.0.tar.gz` from codeload.github.com, sha256 `e32948056bd2604cdcc7fb384155feaf52f05512e02f4e8a7368af48e22f30f2` (`PKG_HASH`) |
| crates.io | bpf-linker 0.11.0 (sha256 `61345fbf1de66aa477e7df1d920175ab807ca52bebd00a04b6171c14aff9e4ca`) names the same commit; the recipe does not use it, and its Cargo.lock differs from the tag's (it omits the `xtask` workspace member and the git patch below) |
| honk's own pin | `.github/ci/pins.env`: `BPF_LINKER_VERSION=0.11.0` (honk's CI installs the release binary) |

- **Lockfile:** 137 packages: 134 from crates.io, each with a checksum, 2 path crates (bpf-linker, xtask) and 1 git package: compiletest-rs from https://github.com/Manishearth/compiletest-rs at `02b122626320f562914710bada39e637f051c7bb`, through `[patch.crates-io]`, a dev-dependency. `rust-host-build.mk` builds with `cargo install --locked` (`RUST_HOST_LOCKED` defaults to 1) and the features `llvm-23,llvm-link-static`.
- **LLVM bindings:** llvm-sys `231.0.0-rc2` (checksum `f4c1483ca6adf171adb0b49d3d9f380e52d68548623a70d8d6b1e266818e4d94`), a release candidate of llvm-sys's LLVM 23 line, with `disable-alltargets-init` and `no-llvm-linking`, so its build script returns before looking for `llvm-config`. bpf-linker's own build script links LLVM statically from `LLVM_PREFIX`, which the recipe sets to the LLVM rustc links (packages patch 0012), with zlib and zstd from the host staging directory and libstdc++ found through the host compiler. llvm-sys 211.0.0 and 221.0.1 are in the lockfile for the other features and are not built.
- **Nothing is downloaded by the build scripts:** bpf-linker's runs the C compiler to locate libstdc++; llvm-sys's exits early.
- **Advisories:** RustSec and OSV match rustix 1.1.3 (RUSTSEC-2026-0486, unsound), reached only through tempfile from the dev-dependency rustc-build-sysroot; it is not built.
- **Role:** it runs on the build host and produces the eBPF object honk loads into the kernel, so a compromised linker could alter that program. Newer releases exist (0.11.1, 0.12.0, 0.13.0); the recipe follows honk's pin.

## honk's own downloads at run time

Not part of the forks, but inputs to the running firmware: honk-core fetches subscriptions from their configured URLs (reqwest with rustls and AWS-LC, the platform verifier). With the native API enabled, it updates geodata automatically by default (every 24 hours, from `raw.githubusercontent.com/MetaCubeX/meta-rules-dat` with `fastly.jsdelivr.net` as fallback), checking each file against a sha256 published beside it on the same host: that detects corruption, not a compromised source. The files land in honk's data directory, which the firmware keeps on the data disk while it is mounted and in RAM otherwise (honk-datapath D5). The default connectivity check is `https://www.gstatic.com/generate_204`.

## Conclusion

**Accepted, with conditions.** Every input is pinned: tag archives by hash, crates by checksum, the forks by full commit, npm packages by sha512. The boring-sys fork is upstream's 5.2.0 package, byte for byte, with BoringSSL as upstream published it, plus about 90 lines of client hooks that only honk's REALITY client calls and that fail closed. The quinn fork changes no crypto, TLS, endpoint or build code. What remains is trust in honk's own author for unreviewed code in the QUIC stack (about 3,100 lines, including a BBRv3 port of an unmerged upstream pull request), a 16-fold relaxation of a bound upstream set against a memory-exhaustion advisory, a fork that falls behind upstream's 0.11.x between manual merges, and a BoringSSL from May 2026 that cannot move until the fork is rebased. There is no upstream alternative: honk calls APIs only the forks have, and its `[patch]` puts the patched BoringSSL in every build.

Conditions:
1. **Build only from the pinned artifacts:** keep `PKG_HASH` and `--locked` (never `RUST_PKG_LOCKED:=0` or `RUST_HOST_LOCKED:=0`), never `cargo update` or override a source for honk, and keep doona's `--frozen-lockfile`.
2. **Keep the git pins fetchable:** keep `$(DL_DIR)/cargo`, or mirror `Glassyiris/boring-sys` and `Glassyiris/quinn`. The boring-sys commit is reachable only from a non-default branch of a repository its owner can delete.
3. **Track quinn by hand:** compare every quinn-rs/quinn advisory and 0.11.x release with the fork's branch, since scanners match only the version the fork claims; at this review 11 upstream commits are missing.
4. **Trust the QUIC peers:** Hysteria2, TUIC and Juicity nodes and DoQ or DoH3 servers can make honk hold far more buffered data than upstream quinn allows; use only nodes and servers you trust.
5. **Treat BBRv3 as experimental:** if Hysteria2 nodes without an upload rate, or nodes set to `bbr`, misbehave, set `HONK_QUIC_BBR=v1` in honk's environment or choose `cubic` on the node.
6. **Keep the doona recipe's pnpm settings:** the store passed as `pnpm_config_store_dir`, since pnpm 11 ignores `npm_config_store_dir`; the lite edition installed explicitly with `pnpm -C apps/lite install --frozen-lockfile`, as doona's release does; `PNPM_VERSION` equal to doona's `packageManager`. The build needs registry.npmjs.org for metadata either way.
7. **Watch BoringSSL and boring releases** for security fixes; one that matters means rebasing the fork, or patching the vendored BoringSSL here.
8. **honk's geodata auto-update stays as honk ships it** (decided 2026-11-13): with the native API enabled, honk replaces `geoip.dat` and `geosite.dat` every 24 hours from MetaCubeX/meta-rules-dat, jsDelivr as fallback, through its own routing. Rules that use them rest on those sources, whose published sha256 detects corruption only; other sources, or none, would be a new decision.
9. **Re-review on every honk upgrade,** and on every doona, pnpm or bpf-linker bump (below).

## Re-check on upgrade

1. **honk's `Cargo.toml`:** is `[patch.crates-io]` still the same owner and repositories? Note the new revs and any new git source; are boring, boring-sys and tokio-boring still pinned exactly?
2. **honk's `Cargo.lock`:** every crates.io package has a `checksum`; every git source carries the full rev; count crates.io, git and path packages; rerun `cargo tree --locked -e normal,build` with the recipe's features for `aarch64-unknown-linux-musl` and `x86_64-unknown-linux-musl`.
3. **boring-sys base:** download the crates.io package of the new version, compare its sha256 with the crates.io index and its tree with the fork's baseline commit (`diff -r`); follow its `.cargo_vcs_info.json` to cloudflare/boring's tag and that tag's BoringSSL submodule, and compare `deps/boringssl` with that BoringSSL commit.
4. **boring-sys changes:** diff the baseline against the pin; only `patches/` and the apply line in `build/main.rs` may change. Read the patch in full; check that it still applies after `boring-pq.patch`; check the build script still fetches nothing and the package holds no binaries.
5. **honk's REALITY caller:** the key still comes from `RAND_bytes` per connection, the callback still seals once and aborts on failure, and `verify_server_certificate` still checks the HMAC; look for any other caller of the hooks.
6. **quinn fork point:** find the merge base with upstream 0.11.x and the latest upstream release it contains; `git cherry` the fork against upstream `main`; has #2481 or any fork change been merged upstream (then prefer upstream)?
7. **quinn changes:** diff the old pin against the new one. `quinn-proto/src/crypto*`, transport parameters, packet protection, Retry and tokens, `quinn-udp`, manifests and build scripts must stay untouched; search added non-test lines for `unsafe`, `extern`, `std::process`, `std::env`, `std::fs`, URLs and new dependencies; read `assembler.rs` (`MAX_CHUNKS`), the flow-control and auto-tuning code and the congestion interface in full.
8. **quinn advisories:** list quinn-rs/quinn's GitHub advisories and the RustSec entries for quinn, quinn-proto and quinn-udp; confirm each fix, or its equivalent, is in the pin; list the upstream 0.11.x commits after the merge base.
9. **All crates:** RustSec and OSV for honk's, honk-ebpf's and bpf-linker's lockfiles; classify each match as firmware or lockfile-only with `cargo tree`; check the licences and build scripts (downloads, processes, prebuilt objects) of crates new to the firmware set.
10. **doona:** the tag's commit equals honk's `DOONA_REVISION`; both lockfiles resolve only from the registry with sha512; `allowBuilds` unchanged, or new entries reviewed; an install with `--ignore-scripts` lists no new lifecycle scripts; `pnpm audit` for both lockfiles, with the paths of any match; `packageManager` equals `PNPM_VERSION`; the build tools and Vite plugins still contain no URL or process start.
11. **pnpm:** the new tarball's sha512 equals the registry's `dist.integrity`; reread its defaults for `verify-deps-before-run`, `strict-dep-builds`, `minimum-release-age` and which environment variables it honours.
12. **bpf-linker:** the version equals honk's `BPF_LINKER_VERSION`; the tag archive's commit equals the crates.io package's `.cargo_vcs_info.json`; every crates.io package has a checksum; the llvm-sys version's LLVM major equals rustc's; the build scripts still fetch nothing.
13. **honk's run-time sources:** the geodata defaults, the connectivity-check default, and any new download path; is the Clash API still left out?

## Not verified

- **No build, test run or traffic capture of either fork.** The boring-sys patch was applied, not compiled; the REALITY hooks were read, not exercised; quinn's tests did not run, and the fork was not tested against a malicious peer.
- **Not a line-by-line read of quinn.** The added non-test lines were searched for risky patterns; the assembler, flow-control, auto-tuning, endpoint and connection changes and the congestion interface were read in full; the BBRv3 controller (about 2,150 lines) was read for its interfaces and randomness, not for correctness, and its tests (about 5,090 lines) were not read.
- **BoringSSL after the pin** was checked by commit subject only.
- **Commit authorship cannot be proven:** the boring-sys commits are unsigned, the quinn fork is partly signed, and the signing key was not checked locally; GitHub's mapping of identities to accounts was taken as reported.
- **Licences** were read from manifest fields, not from the licence texts, apart from BoringSSL's, aws-lc-sys's, jemalloc's and SQLite's.
- **doona's install scripts** were listed from an install on darwin/arm64; the Linux-only platform packages were not unpacked. The implicit lite install and the minimum-release-age check were read from pnpm's source and an install on macOS, not observed in the recipe's build on the build host. The built bundles were not inspected.
- **pnpm's registry signature and provenance** were not verified; only its sha512 was compared.
- **What `-Zbuild-std=core` fetches** for the standard library's lockfile, and whether `cargo install --locked` fetches bpf-linker's git dev-dependency, were not checked.
- **Whether the private configuration enables the native API**, and with it the geodata updates, was not checked.
