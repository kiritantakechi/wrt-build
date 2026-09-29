# dae: review of the forked dependencies

Reviewed: 2026-09-29 (r4s-ebpf-datapath task 1.2). dae v2.1.1 takes three modules from one personal fork owner, `olicesx`: outbound (the proxy protocols), quic-go and qpack (its QUIC stack).

Subject: dae v2.1.1, tag `v2.1.1`, commit `dbae2e82d3ed5324e1648548720f8bbc8cde3882`, the version `feed/net/dae/Makefile` packages (`dae-full-src.zip`, sha256 `880d56d2f4b80c009c29693a5ec1d6a44b4958aeba6323af879787934ee0e855`).

## Pinned version

dae keeps the upstream module path in `require` and swaps in the fork with a `replace` ([go.mod](https://github.com/daeuniverse/dae/blob/dbae2e82d3ed5324e1648548720f8bbc8cde3882/go.mod)):

| Item | Value |
|---|---|
| `require` (L10) | `github.com/daeuniverse/outbound v0.0.0-sticky-ip.0.20260911162531-896954f65c52` |
| `replace` (L136) | `github.com/daeuniverse/outbound => github.com/olicesx/outbound v0.0.0-sticky-ip.0.20260918090140-cc86ced2e683` |
| Resolved commit | `cc86ced2e683b91387f2cde7cfcadcb5ac2adbc3` (2026-09-18, "fix(reality): keep the REALITY ClientHello post-quantum free"), tip of fork branch `perf/complete-optimizations` |

go.sum (L226–227):

```
github.com/olicesx/outbound v0.0.0-sticky-ip.0.20260918090140-cc86ced2e683 h1:KpOAxQzPu67zF2ONe+6AIQCjxjXOQQgLswvtekP16jY=
github.com/olicesx/outbound v0.0.0-sticky-ip.0.20260918090140-cc86ced2e683/go.mod h1:AuXipZhyrHm/ebwky2LR1NNqvIyAq9i1W/0RVvCZ+Xs=
```

Verification:
- **Proxy and checksum database agree.** `go mod download -json` through proxy.golang.org and sum.golang.org returned the same `Sum` and `GoModSum`, with `Origin.Hash` = `cc86ced2e683…`. The module zip is identical to `git archive cc86ced2e683`.
- **No vendored copy.** `dae-full-src.zip` has no `vendor/` directory, and its go.mod and go.sum are byte-identical to the tag. Modules come from the Go proxy at build time, and go.sum enforces their hashes.
- **No overrides in our build.** wrt-build overrides none of GOPROXY, GOSUMDB or GOFLAGS.
- **The `require` version is not an upstream version.** The base tag `v0.0.0-sticky-ip` and commit `896954f65c52` exist only in the fork; `896954f` is an ancestor of `cc86ced`. go.sum has no `daeuniverse/outbound` lines, so the build works only through the `replace`.

The same owner supplies two more modules, reviewed below in "The quic-go and qpack forks": `github.com/olicesx/quic-go v0.0.0-20260910141758-62d80bbebb5b` (a direct `require`, L17, plus a self-`replace`, L116) and `github.com/olicesx/qpack v0.6.1-0.20260910092525-3d8903e3255f` (indirect).

## Fork point and upstream comparison

- **Fork:** https://github.com/olicesx/outbound, a GitHub fork of `daeuniverse/outbound` created 2026-02-16; owner `olicesx` ("kix").
- **Merge base:** [`00c4fbb38759a34c2693030dfc5947794d97dd5b`](https://github.com/daeuniverse/outbound/commit/00c4fbb38759a34c2693030dfc5947794d97dd5b) ("hysteria2: support port hopping (#39)", 2025-07-22), exactly the upstream commit dae v1.1.0 pinned (`h1:aklFtuD9AJ9toFveiPNfstY0o4owduvJ+iNpc61mhkU=`). The fork's `main` branch still points at it; all fork work lives on topic branches.
- **Comparison:** [compare 00c4fbb…cc86ced](https://github.com/daeuniverse/outbound/compare/00c4fbb38759a34c2693030dfc5947794d97dd5b...olicesx:outbound:cc86ced2e683b91387f2cde7cfcadcb5ac2adbc3): 356 commits ahead, 0 behind. Upstream `main` ([`cfd9e39`](https://github.com/daeuniverse/outbound/commit/cfd9e39fd5e024fe62c7ad68ffd09bb452b10df4), 2026-06-23) has one commit the fork lacks, whose equivalent the fork carries (`realityECDHEKey`); upstream has no tags.
- **Size of the diff** (local `git diff`; the GitHub API stops at 300 files):

  | Part | Files | Lines added | Lines removed |
  |---|---|---|---|
  | All | 440 | 68,368 | 3,851 |
  | Non-test Go | 184 | 20,135 | 3,710 |
  | Test Go | 248 | 47,493 | 108 |
  | Other (CI workflow, one script, docs, go.mod/go.sum) | 8 | 740 | 33 |

- **Authorship:** no commit is signed, apart from GitHub web merges. `kix <olices@9up.in>` 269, `kix-e2e <e2e@kix.local>` 65, `olicesx <olices@9up.in>` 17, and one each from QiuSimons (later reverted), Kaede Akino (the Shadowsocks 2022 port) and `AI Builder Bot <bot@example.com>`; two fork branches are named `codex/*`.
- **Upstream review:** the only olicesx pull request to `daeuniverse/outbound` (#63, Shadowsocks 2022) is still open. The fork pins entered dae through olicesx's PRs [#980](https://github.com/daeuniverse/dae/pull/980), [#1099](https://github.com/daeuniverse/dae/pull/1099) and [#1101](https://github.com/daeuniverse/dae/pull/1101), each approved and merged by one dae maintainer.

Which outbound each dae release used:

| dae | outbound source | Commit |
|---|---|---|
| v1.1.0 | `daeuniverse/outbound` (upstream) | `00c4fbb38759` |
| v2.0.0rc1 | `olicesx/outbound` | `8de5a31bdbe1` |
| v2.0.0 (also ImmortalWrt's current `net/dae`) | `olicesx/outbound` | `52c26f8e759e` |
| v2.1.0, v2.1.1 | `olicesx/outbound` | `cc86ced2e683` |

Between the v2.0.0 pin and the v2.1.1 pin: 226 commits, 375 files, +48,163 / −4,764 lines.

## Changes

Every package below is compiled into dae, because `component/outbound` blank-imports every dialer and protocol.

New protocols and link options:
- **Shadowsocks 2022** (`protocol/shadowsocks_2022`), ported from LostAttractor/next: BLAKE3 key derivation (`lukechampine.com/blake3`), a timestamp window, a sliding-window UDP replay filter and a response-salt check.
- **NaiveProxy client** over HTTP/2 CONNECT with padding (`dialer/naive`, scheme `naive+https`; `naive+quic` is rejected).
- **ShadowTLS v1–v3** as a transport and as a Shadowsocks plugin (`transport/shadowtls`), with `sagernet/sing` and `sagernet/sing-shadowtls`.
- **Hysteria2:** Salamander obfuscation, an ECH config list (`ech=`), a custom CA file (`ca=`, a local path), upload/download Mbps parameters, and a changed `pinSHA256` meaning (below).
- **VMess TCP HTTP-header obfuscation** (`transport/httpheader`).
- **More uTLS fingerprints** (`chrome_106_shuffle`, `chrome_120`, `chrome_131`, `chrome_133`, `firefox_120`, `android`); lookup is case-insensitive and an unknown name is rejected when the node is created.
- **Subscription parser** (`dialer/subscription.go`): parses share links; fetches nothing.
- **Sticky IP** (`dialer/stickyip`): caches a proxy server's resolved address for 5 minutes, per TCP/UDP and IPv4/IPv6, through the system resolver.

Congestion control:
- **Experimental BBRv3** (`protocol/tuic/congestion/bbr3`), selectable with a new `cc_override` link parameter (`bbr`, `cubic`, `new_reno`, `brutal`, `bbr3`).
- **Default changed:** TUIC, Juicity and Hysteria2 use bbr3 when no fixed rate is negotiated, Brutal when one is. The default flipped to bbr3 on 2026-09-15, three days before the pin; `cc_override=bbr` restores the previous behaviour.
- **TUIC:** `ReduceRtt` (QUIC `DialEarly`) is always on; the maximum datagram frame size went from 1400 to 1452.

REALITY and TLS:
- **REALITY authentication always uses AES-256-GCM,** instead of choosing through a `go:linkname` into a private uTLS function, which is gone.
- **No post-quantum key share by default:** the REALITY ClientHello no longer offers X25519MLKEM768. On an authentication failure it retries once with the other hello shape, then backs off for 5 minutes, and remembers per server which shape worked.
- **The spider (cover traffic) is bounded:** panic recovery, a 30 s per-request timeout, a 1 MiB body limit, a capped path set; a malformed `spiderX` fails at config load.
- **`uTLSConfigFromTLSConfig` copies every relevant setting** (RootCAs, VerifyPeerCertificate, NextProtos, cipher suites, curves, versions, session cache); upstream copied only ServerName and InsecureSkipVerify.
- **Write coalescing** below crypto/tls and uTLS (`pkg/coalesce`), flushed after every write; handshakes honour the dial context.

Plumbing, performance and robustness (most of the volume): bounded unwrapping of wrapper connections, a buffered reader and write deadlines in `netproxy`; an epoll-based UDP receiver and a refactored resolver in `protocol/direct` (SO_MARK is still applied on every dial path); a reworked buffer pool; lifecycle and close-race fixes across trojan, vless/vision, vmess, socks5, http, anytls, juicity, tuic, hysteria2, SSR, simple-obfs, meek, gRPC, ws and mux. Removed: server-side gRPC, `pkg/disk_bloom`, unused helpers, and the "iodized" Shadowsocks salt generator. Dependencies: `olicesx/quic-go` and `olicesx/qpack` instead of `daeuniverse/quic-go`; utls 1.6.4 → 1.8.2; new `sagernet/sing` 0.6.0, `sing-shadowtls` 0.2.0, `samber/oops` 1.19.4 (pulls in the OpenTelemetry API only, no SDK or exporter) and `blake3` 1.4.1; `cloudflare/circl` dropped.

## Security-relevant findings

- **No new network endpoints.** No new hard-coded hosts, URLs or IP literals in the 20,376 added non-test lines. One hard-coded fetch was removed (the salt generator's `http.Get("https://github.com/explore")`); outbound connections go only to configured nodes, and the REALITY spider's requests to `https://<serverName>` predate the fork and are now bounded.
- **No telemetry.** "Telemetry" in bbr3 means in-process counters; dae's go.sum has no exporter modules.
- **No hidden code execution or obfuscation:** no `os/exec`, `plugin`, `go:generate`, `go:embed`, cgo, assembly, binary blobs, generated files or long encoded literals; `go:linkname` went from one use to none. `unsafe` and `reflect` read private uTLS fields for REALITY and XTLS Vision (as upstream, now with type checks), and `unsafe.String` builds map keys.
- **File access:** only Hysteria2 `ca=` reads a local PEM file, at a path from the node link.
- **Stricter TLS verification:** the uTLS path now honours RootCAs and VerifyPeerCertificate (upstream dropped them, skipping custom CA and pin checks with `tls_implementation: utls`); the gRPC and meek connection caches no longer share a connection between an insecure and a verified node on the same address.
- **Changed or looser TLS verification:**
  - **Hysteria2 `pinSHA256`** now turns on InsecureSkipVerify and checks only the leaf certificate's SHA-256. Upstream accepted a pin of any certificate in the chain and still verified CA and hostname. A leaf pin is a sound anchor, but pinning an intermediate or CA no longer works, and CA checks no longer apply on top of a pin.
  - **AnyTLS** honours dae's global `allow_insecure` as every other protocol does; upstream honoured only the link's own flag.
- **Cryptography:** REALITY AES-GCM-only matches Xray-core and XTLS/REALITY. Dropping X25519MLKEM768 removes post-quantum key exchange for REALITY and makes `chrome` fingerprints differ from real Chrome 131+: a fingerprinting concern, not a loss against classic X25519. Shadowsocks 2022, naive padding, the ShadowTLS glue and Salamander have had no review outside the fork. `math/rand` serves obfuscation and padding only (Salamander salts, as upstream Hysteria; AnyTLS padding lengths). TUIC always dials early, but no session cache is configured, so no replayable 0-RTT data should be sent (read from the code, not tested).
- **Supply chain:** one maintainer, unsigned commits, no upstream review, about 20k non-test lines in 7 months, signs of AI-tool involvement; the same owner supplies dae's QUIC stack. The exact pseudo-version, the go.sum hash (confirmed by sum.golang.org) and `PKG_HASH` mean a force-push to the fork cannot change what we build.
- **Licensing:** `sagernet/sing` and `sing-shadowtls` are GPL-3.0-or-later, compatible with dae's AGPL-3.0-only. The Salamander port credits apernet/hysteria as AGPL-3.0, which is MIT: an attribution mistake only.

## The quic-go and qpack forks

| Module | Version | go.sum `h1:` | Commit (branch) |
|---|---|---|---|
| `github.com/olicesx/quic-go` | `v0.0.0-20260910141758-62d80bbebb5b` | `MLp1BCIfVjs6q3OHuHRwmD/HhEPWLnyFvr07uPZJqSQ=` | `62d80bbebb5b` (`fix/audit-20260907`) |
| `github.com/olicesx/qpack` | `v0.6.1-0.20260910092525-3d8903e3255f` | `hjUaM52me7aDLXAw9/mkwIpGRnj8ayskzxe3l3h8HPE=` | `3d8903e3255f` (`fix/typed-decode-errors`) |

- **The pins hold.** proxy.golang.org, sum.golang.org and a rebuild from git (`GOPROXY=direct GOSUMDB=off`) all give the go.sum hashes, so the module zips are exactly the git trees reviewed. outbound requires the same quic-go version, and dae v2.1.0 has the same pins. Both commits are unsigned and sit on non-default branches.
- **Linked into dae** (`go list -deps`, linux/arm64): the quic-go root package, `congestion`, `http3`, `quicvarint`, `logging`, `internal/*`, and qpack. `qlog` and `metrics` are not linked, so neither the Prometheus client nor gojay is in the binary.

**quic-go is three layers on upstream v0.49.0** (`c385cd10`, the merge-base, and the smallest diff of the candidate tags: 166 files, +7,766/−1,038):

| Layer | Commit | Content |
|---|---|---|
| apernet/quic-go `v0.49.0-mod` (Hysteria) | `22292ed0` | pluggable congestion control (the public `congestion` package, `SetCongestionControl`), server-side migration without path validation, an AVL tree for stream gaps, larger windows and buffers |
| daeuniverse/quic-go `sid` (dae v1.1.0's pin) | `2083199a` | `Config.CapabilityCallback`, the module rename |
| olicesx, 67 commits (2026-02 to 2026-09) | `62d80bbe` | backports of upstream security fixes (GHSA-47m2-4cr7-mhcw; incremental QPACK decoding with a decoded-size limit for GHSA-g754-hx8w-x2g6 and GHSA-vvgj-x9jq-8cj9), other upstream fixes, HTTP/3 behaviour aligned with upstream v0.61, GSO batching, a raw `recvmmsg` reader, pooled DATAGRAM buffers (`Connection.ReleaseDatagram`), lifecycle fixes; non-test source +1,806/−399 |

**qpack** is a GitHub fork of upstream v0.6.0 (`1661efa`) with 6 commits (library code about +120 lines): typed decoder errors for http3, RFC 9204 §4.5.1.2 Delta Base parsing (the dynamic table stays unsupported), and an encoder that refuses fields after a failed write.

Security-relevant findings:
- **Nothing new of the kinds searched for:** no endpoints, URLs, telemetry, `os/exec`, cgo, `go:embed`, blobs or new third-party requires. The only `go:linkname` is upstream's, in the unchanged `internal/qtls`.
- **The crypto path is unchanged:** AEAD, header protection, key derivation, Retry, tokens, stateless reset and certificate handling. `internal/handshake` only makes the key-update intervals atomic (same defaults) and skips a session ticket in a server-only Go 1.25 case. dae and outbound only dial, so the server-side migration and 0-RTT acceptance paths are unreachable.
- **`unsafe` in the `recvmmsg` reader** (`sys_conn_skipaddr.go`, Linux, client dials only): the header layout matches the kernel's `struct mmsghdr` with compile-time width checks, the `uintptr` conversion is in the call expression, and `go vet` passes for arm64, arm and amd64.
- **The shared pools depend on each buffer being released exactly once;** a double release would mix data between two connections inside dae. dae never calls `ReleaseDatagram`; outbound's hysteria2 and tuic clients do. The fork's history has four double-release fixes.
- **A peer can cost more memory:** the stream gap limit rose from 1,000 to 20,000. The peer is a configured proxy node or a DoQ/DoH3 server.
- **Advisories:** all 8 upstream quic-go advisories (checked 2026-09-29) are fixed before v0.49.0, do not apply, or are backported; qpack has none. But **scanners will miss future ones:** govulncheck and OSV match on the module path, and this is `olicesx/quic-go`.
- **Stale:** 570 upstream commits behind (v0.50.0 to v0.63.0). The fork's `docs/upstream-sync-ledger.tsv` waives v0.50.0 to v0.62.0 pending a rebase, so upstream fixes that came without an advisory are generally missing.
- **Tests:** `go test -race` passes for the root package, `http3`, `internal/...`, `quicvarint` and qpack (darwin/arm64; the Linux-only paths did not run).

**Accepted, with conditions:** the content is exactly what go.sum pins, the diff has no endpoints, exec, cgo or crypto changes, and every known advisory is covered. There is no drop-in upstream: dae and outbound use APIs only the fork has (`SetCongestionControl`, `congestion`, `CapabilityCallback`, `ReleaseDatagram`).

## Conclusion

**Accepted, with conditions.** There are no backdoor indicators, most TLS-relevant changes tighten verification, the artifact is pinned, and there is no upstream alternative: every dae release since v2.0.0rc1, including ImmortalWrt's current package, depends on this fork, so rejecting it would mean dae v1.1.0. What remains is trusting one maintainer, reviewed by nobody else, for about 20k lines of proxy and crypto code and the QUIC stack.

Conditions:
1. **Build only from the pinned artifacts:** keep `PKG_HASH`, and never relax Go's checks for this package (`GOFLAGS=-mod=mod`, `GONOSUMDB`, `GONOSUMCHECK`, `GOPRIVATE`, `GOSUMDB=off`, or a direct-only `GOPROXY`).
2. **Treat bbr3 as experimental:** if TUIC, Juicity or Hysteria2 nodes misbehave, set `cc_override=bbr` on those links.
3. **Avoid insecure node links.** For Hysteria2, use a leaf-certificate `pinSHA256` or a proper CA, knowing that a pin now replaces CA checks.
4. **Track quic-go and qpack advisories by hand,** since scanners will not match the forked module path (above).
5. **Smoke-test the QUIC users** (DoQ, DoH3 and the hysteria2, tuic and juicity outbounds) on the target before relying on them.
6. **Re-review on every dae upgrade** (below).

## Re-check on upgrade

1. **dae go.mod:** is the `replace github.com/daeuniverse/outbound => github.com/olicesx/outbound …` still there? Note the new pseudo-version and commit, and any new `replace` lines.
2. **go.sum:** confirm the `h1:` lines of `olicesx/outbound`, quic-go and qpack with `go mod download -json <module>@<version>` (`Sum`, `GoModSum`, `Origin.Hash`).
3. **`dae-full-src.zip`:** still no `vendor/`, and go.mod and go.sum equal the tag's.
4. **Diff the old pin against the new one** in a clone with the fork as a remote. Search the added non-test lines for URLs and IP literals, `net/http` clients, `os/exec`, `go:linkname`, `go:generate`, `go:embed`, `unsafe`, `reflect`, `InsecureSkipVerify`, `VerifyPeerCertificate`, `RootCAs`, `init()` and new requires; read changes to `transport/tls/*` and `dialer/*` in full.
5. **Upstream status:** has `daeuniverse/outbound` absorbed the fork (then prefer upstream)? Has the pin moved off a branch tip?
6. **Congestion control and 0-RTT:** is bbr3 still the default, has the `cc_override` list changed, is TUIC still dialing early without a session cache?
7. **Certificate checks:** the Hysteria2 pin and CA behaviour, and any new link parameter that turns verification off.
8. **New third-party dependencies** and their licences.
9. **quic-go and qpack:** is the merge-base still v0.49.0 (or rebased)? Diff the old pin against the new one; `internal/handshake`, `internal/qtls`, the packet packer and unpacker and the Retry/token code must stay untouched; read `sys_conn_skipaddr.go` and any new `unsafe` or syscall code, the pool code (`internal/wire/pool.go`, `datagram_queue.go`, `receive_stream.go`, `send_stream.go`, `frame_sorter.go`) and outbound's `ReleaseDatagram` callers; does the fork's ledger cover every upstream release and advisory; is qpack still close to an upstream tag?

## Not verified

- **Not a full line-by-line read.** All 20,135 added non-test lines were searched for risky patterns; the TLS/REALITY code, the Hysteria2 dialer, naive, ShadowTLS, sticky IP, the subscription parser, the salt generator, the transport and gRPC caches and the congestion-controller selection were read in full.
- **No dynamic testing:** no build, test run or traffic capture of the fork itself.
- **Commit authorship cannot be proven,** since the commits are unsigned.
- **REALITY claims were checked against source only,** not against live servers.
- **Protocol correctness was not assessed** for bbr3, Shadowsocks 2022, naive or ShadowTLS.
- **quic-go:** the Linux-only paths (`recvmmsg`, GSO, ECN, Don't Fragment), the interop runner and the fuzzers did not run; the added test code (about 4.4k lines) and the apernet AVL tree and congestion adapter were not read line by line; upstream fixes without an advisory were not checked one by one; the fork was not tested against a malicious peer.
