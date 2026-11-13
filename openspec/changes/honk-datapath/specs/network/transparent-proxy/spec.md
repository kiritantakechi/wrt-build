## MODIFIED Requirements

### Requirement: Bind LAN-side interfaces only
honk SHALL bind only br-lan, plus podman0 and tailscale0 when they exist. honk MUST NOT attach programs to any WAN interface. On the cgroup2 root honk SHALL attach only its `sock_ops` program, which acts only on sockets in honk's own network namespace, and its socket-identity programs, which record the process that owns a socket and allow every socket operation; honk MUST NOT redirect, mark or refuse the router's own sockets. A bound interface that appears after honk starts SHALL be bound within 60 seconds of appearing, also while honk is still starting or reloading.

#### Scenario: Check programs on each interface
- **WHEN** honk is running and the BPF programs attached to br-lan and pppoe-wan are inspected
- **THEN** br-lan has honk programs, and pppoe-wan has no honk programs at all

#### Scenario: Check the cgroup programs
- **WHEN** honk is running and the BPF programs attached to the cgroup2 root are inspected
- **THEN** honk's programs there are its `sock_ops` program and its socket-identity programs on socket creation, `connect` and `sendmsg`, and nothing else; the router's own connections go out direct

#### Scenario: Container bridge appears after the proxy
- **WHEN** honk is already running and only then podman0 is created
- **THEN** within 60 seconds honk programs appear on podman0, and container traffic starts being split by rule

#### Scenario: Container bridge appears while the proxy starts
- **WHEN** podman0 is created right after honk was started anew, before honk is ready
- **THEN** within 60 seconds honk programs appear on podman0

### Requirement: Rule-based traffic splitting
Traffic from bound interfaces SHALL be split by honk's rules:
- Direct traffic SHALL be forwarded directly by the kernel, without entering honk's user space;
- Proxied traffic SHALL leave through the configured proxy node.

#### Scenario: Access a direct target
- **WHEN** a LAN client accesses a target that the rules classify as direct
- **THEN** the connection succeeds, the target sees the router's WAN address as the source, and the router shows no connection from the honk process to that target

#### Scenario: Access a proxied target
- **WHEN** a LAN client accesses a target that the rules classify as proxied
- **THEN** the connection succeeds, and the target sees the proxy node's egress address as the source

### Requirement: Router-originated traffic goes direct
Traffic originated by the router's own processes MUST NOT be proxied through honk.

#### Scenario: Router accesses an external address
- **WHEN** a command on the router accesses an external address that the rules would otherwise classify as proxied
- **THEN** the target sees the router's WAN address as the source

### Requirement: Optional CPU pinning
honk SHALL be placed by the scheduler by default. An option SHALL pin it to the board's big cores instead: the CPUs with the highest capacity. These are the Cortex-A72 cores cpu4-5 on the NanoPi R4S, and the Cortex-A76 cores cpu4-7 on the NanoPi R6S.

#### Scenario: Enable CPU pinning
- **WHEN** the pinning option is enabled and honk restarts
- **THEN** honk runs only on the CPUs with the highest capacity, and its programs are on the bound interfaces again

### Requirement: Configuration management
honk's configuration SHALL be editable in LuCI, and saving it SHALL hot-reload honk without ending the honk process. The full configuration (subscriptions, node information and the native API token) MUST NOT be preinstalled in the firmware image; its canonical copy lives in the private config repository. honk SHALL start at boot only while its start-at-boot switch is on.

#### Scenario: Save config in LuCI
- **WHEN** the honk config is modified and saved in LuCI
- **THEN** honk hot-reloads to apply it, the same honk process keeps running, and direct traffic is not interrupted during the reload

#### Scenario: Inspect the image
- **WHEN** the honk config in the firmware image is inspected
- **THEN** it contains only a template without subscriptions, node information or a native API token, and the template leaves the native API off

#### Scenario: Turn the proxy off
- **WHEN** honk runs, it is stopped in LuCI, and its start-at-boot switch is turned off there
- **THEN** honk stops, no honk programs remain on the bound interfaces, and honk does not start at the next boot

### Requirement: Fall back to direct when stopped
When honk stops or crashes, the honk programs on bound interfaces SHALL be removed, and LAN traffic SHALL fall back to direct forwarding by the kernel.

#### Scenario: Stop the proxy
- **WHEN** the honk service is stopped
- **THEN** LAN clients can still reach external networks, and all traffic goes direct

### Requirement: Register a health check
honk SHALL register a check with the health check: the check passes only when honk is running and its programs are attached to every bound interface that currently exists.

#### Scenario: Proxy not running
- **WHEN** the health check runs while the honk process is not running
- **THEN** the honk check fails

## ADDED Requirements

### Requirement: The router stays reachable from bound interfaces
While honk runs, connections from a bound interface to the router's own addresses SHALL reach the router's services, over IPv4 and IPv6.

#### Scenario: Connect to the router from the LAN
- **WHEN** honk runs and a LAN client opens TCP connections to the router's LAN address, one every second for a minute
- **THEN** every connection is accepted and answered by the router's service

### Requirement: Web UI through the native API in token mode
honk's web UI SHALL be served only through honk's native API, and only in static-token mode. The native API SHALL be off unless the configuration enables it, MUST answer only from the LAN zone, and MUST NOT accept configuration writes.

#### Scenario: Native API enabled with a token
- **WHEN** a configuration that enables the native API with a token is applied
- **THEN** the web UI opens from a LAN client with that token, and an API request from the LAN without the token is refused

#### Scenario: Native API from outside the LAN
- **WHEN** the native API is enabled and a request to it comes from the WAN or from the container bridge
- **THEN** it gets no response

### Requirement: honk's netfilter hook outlives firewall reloads
honk's own nftables table SHALL stay in place, unchanged, through every reload of the firewall while honk runs, and SHALL be gone once honk has stopped.

#### Scenario: Reload the firewall
- **WHEN** honk runs and the firewall reloads
- **THEN** honk's nftables table is still there with the same rules

#### Scenario: Stop the proxy after a reload
- **WHEN** the firewall has reloaded and honk is then stopped
- **THEN** honk's nftables table is gone

### Requirement: No other listeners
In the router's own network namespace, honk SHALL listen on no port other than its DNS listener on the loopback address and, when enabled, the native API.

#### Scenario: Inspect honk's sockets
- **WHEN** honk runs with the native API off and the listening sockets of the router's network namespace are inspected
- **THEN** honk's only listener there is the DNS listener on 127.0.0.1
