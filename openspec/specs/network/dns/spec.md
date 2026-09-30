# network/dns Specification

## Purpose
Define the LAN DNS path: dnsmasq handles DHCP and local hostnames, and queries for external domains go to dae, which performs the resolution that domain-based splitting needs.

## Requirements

### Requirement: dnsmasq remains the LAN DNS server
DHCP SHALL hand out the router's LAN address to clients as the DNS server. Queries for local hostnames (`.lan`) SHALL be answered by dnsmasq itself.

#### Scenario: Query a local hostname
- **WHEN** a LAN client queries another client's `<hostname>.lan`
- **THEN** it gets the other client's LAN address, and the query does not go through dae

### Requirement: External domains resolved by dae
dnsmasq SHALL forward all non-local queries to dae's DNS listener on the loopback address, and dae resolves them according to its upstream rules.

#### Scenario: Query an external domain
- **WHEN** a LAN client queries an external domain
- **THEN** the query is forwarded to dae, dae's log records the query, and the client gets a result

### Requirement: Fall back to upstream DNS without dae
When dae's DNS listener is unavailable, dnsmasq SHALL keep resolving with the upstream DNS obtained on WAN, so the LAN is not cut off.

#### Scenario: Resolve after dae stops
- **WHEN** a LAN client queries an external domain after dae is stopped
- **THEN** it still gets a result

### Requirement: dae DNS port not exposed
dae's DNS listener MUST bind only to the loopback address, and it MUST NOT be reachable from LAN or WAN.

#### Scenario: Query dae's DNS port from LAN
- **WHEN** a LAN client sends a query to the dae DNS port on the router's LAN address
- **THEN** the query gets no response
