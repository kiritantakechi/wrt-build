# Tasks

## 1. Packaging

- [ ] 1.1 Add dae 2.1.1 to our own feed: start from ImmortalWrt's Makefile, compile the BPF with the host clang, and verify Go modules against `go.sum`. Verification: the CI build succeeds; an emulator test confirms that `dae --version` prints 2.1.1.
- [ ] 1.2 Review the diff between the version of `olicesx/outbound` pinned in `go.sum` and upstream `daeuniverse/outbound`, and write the conclusion in `docs/supply-chain/dae.md`. Verification: the document contains a diff summary and a conclusion on whether it is accepted; if the conclusion is not to accept it, resolve that before continuing with later tasks.
- [ ] 1.3 Add luci-app-dae. Verification: covered by the "Save config in LuCI" test in `test_transparent_proxy.py`.
- [ ] 1.4 Add einat to our own feed: aya loader only, the ipv6 feature disabled, and Rust dependencies verified against `Cargo.lock`. Verification: an emulator test confirms that `einat --version` prints 0.1.11; the image audit confirms that the executable does not depend on libbpf or libelf (`readelf -d`).
- [ ] 1.5 Write the einat mark patch (design D2) and prepare the submission materials in `docs/upstream/`, but do not submit them. Verification: the accept test in `test_nat.py` confirms that the counter of the accept-by-mark rule increases; when `--inbound-mark` is not set, another test confirms that packets are not marked.
- [ ] 1.6 Add `config/datapath.seed`: kmod-sched-core, kmod-sched-bpf, kmod-veth, kmod-sched-cake, qosify, dae, luci-app-dae, einat, bpftool-minimal. Verification: the line-by-line validation of `just config ci` passes.

## 2. Mark allocation table

- [ ] 2.1 Create `config/marks.tsv` with the initial contents from design D4. Verification: `editorconfig-checker` passes; every row has four columns, and every mask is a valid hexadecimal number.
- [ ] 2.2 Implement `scripts/marks-check.sh` and wire it into `just check`. Verification: the "Overlapping mark configured" test in `tests/network/test_tc_hook_order.py` (host-only) writes a mark that overlaps dae's into a fixture template, and the check fails and reports both conflicting parties; after the mark is removed, the check passes.

## 3. Emulated ISP and internet (design D11)

- [ ] 3.1 Add rp-pppoe, ppp, kea, radvd, dnsmasq, microsocks, iperf3, and iputils to the flake's test tool group; `prepare-runner.sh` and `docs/dev-setup.md` take care of loading `ppp_generic` and `ppp_async` and opening up the permissions of `/dev/ppp`; `env-report` checks both. Verification: `just env-report` prints the tool versions and the ppp check results; without ppp support, it reports an error and gives the fix.
- [ ] 3.2 Add the `client-b`, `inet`, and `proxy` namespaces and the `br-inet` bridge to the topology declaration in `wrt_tests/net.py`. Verification: `tests/unit/test_net.py` builds the topology without starting the emulator and confirms that the addresses and routes of each namespace match design D11.
- [ ] 3.3 Implement the `isp` side: a user-mode pppoe-server, radvd and kea-dhcp6 started per session, and an address pool that hands out a different address on each redial. Verification: `tests/unit/test_isp.py` dials with pppd in the sandbox as the client and gets an address from the pool and a /56 prefix; after the session is ended and redialed, it gets a different address.
- [ ] 3.4 Implement `wrt_tests/netprobe.py`: UDP/TCP whoami (returns the peer's address, port, and MSS), "big" mode (returns a 3000-byte UDP reply), and sending and receiving raw ESP packets. Also run an authoritative dnsmasq for example.test and iperf3 in `inet`, and microsocks in `proxy`. Verification: `tests/unit/test_netprobe.py` covers every netprobe mode between two plain network namespaces.

## 4. WAN, firewall, and einat integration

- [ ] 4.1 Generate the WAN and LAN config with uci-defaults: PPPoE without credentials, `ipv6 auto`, `mtu_fix 1`, `flow_offloading 1`, `ip6assign 64`, each written only when the option is not yet set. Verification: covered by `test_wan.py`; another test modifies the config, performs a config-preserving upgrade, and confirms that the modified values were not overwritten.
- [ ] 4.2 Write the einat init script: inject the two firewall rules from design D3 through procd, and pass `--inbound-mark` and the port range. Verification: covered by `test_nat.py`; its "Stop einat" test confirms that the two rules disappear along with einat.
- [ ] 4.3 Register `/etc/healthcheck.d/50-einat`. Verification: the health check test in `test_nat.py` covers three cases: it fails when einat is not running; it passes when einat is running but pppoe-wan does not exist; it fails when pppoe-wan exists but einat is not attached to it.

## 5. dae integration

- [ ] 5.1 Implement the config layout from design D5: `config.dae` in the image only does the include; the init script generates `generated/10-bind.dae`; the `user/` directory is left empty with an example provided. Verification: `test_transparent_proxy.py` covers the splitting tests with a test config (a socks5 node pointing at `proxy`); the include merge semantics are settled by the test results, and the conclusion goes into the risk notes of the design.
- [ ] 5.2 Implement hotplug: when podman0 or tailscale0 appears or disappears, regenerate the bind fragment and run `dae reload`. Verification: covered by the "Container bridge appears after dae" test (in the emulator, `ip link add podman0 type bridge` stands in for a real container), plus another test that confirms dae keeps running after the interface is deleted.
- [ ] 5.3 Add an optional CPU pinning parameter to the init script, off by default (design D5). Verification: the emulator has 6 vCPUs; after a test turns the parameter on, `taskset -p $(pidof dae)` shows cpu4-5.
- [ ] 5.4 Register `/etc/healthcheck.d/50-dae`. Verification: the health check test in `test_transparent_proxy.py` covers three cases: it fails when dae is not running, it fails when programs are missing, and it passes when everything is in order.

## 6. DNS

- [ ] 6.1 Configure dnsmasq: `server=127.0.0.1#5353` first, `strictorder` enabled, and the upstreams obtained on WAN kept; set dae's `dns.bind` to 127.0.0.1:5353. Verification: `test_dns.py` covers every scenario of the dns spec.

## 7. QoS

- [ ] 7.1 Configure qosify: egress only, set the upload bandwidth and encapsulation overhead, mode diffserv4 with nat and host_isolate, plus port rules for gaming and video conferencing. Verification: `test_qos.py` covers every scenario of the qos spec.

## 8. Emulator tests (all run in `just test`)

- [ ] 8.1 `tests/network/test_tc_hook_order.py`: the program list and order on both ports; ICMP replies and fragmented UDP replies arrive intact, and qosify's ingress counters increase; restart qosify, einat, and dae in turn and then redial, with the order unchanged after each step; for the mark conflict test, see 2.2. Verification: all tests pass.
- [ ] 8.2 `tests/network/test_nat.py`: endpoint-independent mapping and endpoint-independent filtering; both spoofed-inbound paths (inside the PPP session and on the eth0 layer 2 segment) are dropped; inbound traffic to a mapped port is accepted; ESP passes in both directions and leaves with the WAN address; fallback after einat stops; local connections are not rewritten; IPv6 is not translated; recovery within 60 seconds after a redial; the health check. Verification: all tests pass.
- [ ] 8.3 `tests/network/test_transparent_proxy.py`: the programs on both ports; the container bridge appears after dae; a direct target (`netprobe` sees the WAN address, and the router has no dae connection to that target); a proxied target and an IPv6 proxied target (they see the address of `proxy`); router-originated access goes direct; saving the config through LuCI's HTTP interface triggers a hot reload, and direct traffic is not interrupted meanwhile; the image contains only a template; fallback to direct after dae stops; the health check; no conntrack warning in dmesg. Verification: all tests pass.
- [ ] 8.4 `tests/network/test_dns.py`: `.lan` hostnames are answered directly by dnsmasq; external domains are resolved through dae and appear in dae's log; fallback to upstream after dae stops; a query to port 5353 from the LAN gets no response. Verification: all tests pass.
- [ ] 8.5 `tests/network/test_qos.py`: cake runs at the configured bandwidth, and the only ifb is `ifb-dns`; with the upload bandwidth set to 20 Mbit/s, `client-a` and `client-b` upload at the same time for 60 seconds and their average rates differ by no more than 20%; traffic that matches a voice rule enters the voice tin; recovery within 60 seconds after a redial. Verification: all tests pass.
- [ ] 8.6 `tests/network/test_wan.py`: the credentials in the image are empty; dial-up succeeds after credentials are pushed; the MSS is at most 1452 and the PMTU is 1492; LAN hosts get addresses within the PD prefix and can reach the IPv6 internet; external connections to internal IPv6 addresses are rejected; during a sustained download the connection carries the `[OFFLOAD]` flag, the source address that `netprobe` sees is always the WAN address, and whether ingress hits the flowtable is recorded. Verification: all tests pass; `spec-coverage` shows no uncovered scenario in this change.
