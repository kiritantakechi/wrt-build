## RENAMED Requirements

- FROM: `### Requirement: External domains resolved by dae`
- TO: `### Requirement: External domains resolved by the proxy`

- FROM: `### Requirement: Fall back to upstream DNS without dae`
- TO: `### Requirement: Fall back to upstream DNS without the proxy`

- FROM: `### Requirement: dae DNS port not exposed`
- TO: `### Requirement: Proxy DNS port not exposed`

## MODIFIED Requirements

### Requirement: dnsmasq remains the LAN DNS server
DHCP SHALL hand out the router's LAN address to clients as the DNS server. Queries for local hostnames (`.lan`) SHALL be answered by dnsmasq itself.

#### Scenario: Query a local hostname
- **WHEN** a LAN client queries another client's `<hostname>.lan`
- **THEN** it gets the other client's LAN address, and the query does not go through honk

### Requirement: External domains resolved by the proxy
dnsmasq SHALL forward all non-local queries to honk's DNS listener on the loopback address, and honk resolves them according to its upstream rules.

#### Scenario: Query an external domain
- **WHEN** a LAN client queries an external domain
- **THEN** the query is forwarded to honk, honk's DNS cache holds the name, and the client gets a result

### Requirement: Fall back to upstream DNS without the proxy
When honk's DNS listener is unavailable, dnsmasq SHALL keep resolving with the upstream DNS obtained on WAN, so the LAN is not cut off.

#### Scenario: Resolve after the proxy stops
- **WHEN** a LAN client queries an external domain after honk is stopped
- **THEN** it still gets a result

### Requirement: Proxy DNS port not exposed
honk's DNS listener MUST bind only to the loopback address, and it MUST NOT be reachable from LAN or WAN.

#### Scenario: Query the proxy's DNS port from LAN
- **WHEN** a LAN client sends a query to the honk DNS port on the router's LAN address
- **THEN** the query gets no response

## ADDED Requirements

### Requirement: DNS to private addresses reaches its server
A DNS query from a bound interface addressed to a private address, the router's own included, SHALL reach the server at that address unchanged, while honk runs.

#### Scenario: Resolve a container's name
- **WHEN** honk runs and a container on the container bridge resolves its Pod's name through its network's resolver
- **THEN** it gets the Pod's address

#### Scenario: Query the router while the proxy runs
- **WHEN** honk runs and a LAN client queries `<hostname>.lan` at the router's LAN address
- **THEN** dnsmasq answers with that client's LAN address, and honk's DNS cache does not hold the name
