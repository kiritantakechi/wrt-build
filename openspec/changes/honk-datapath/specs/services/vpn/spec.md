## MODIFIED Requirements

### Requirement: Relation to the transparent proxy
Traffic entering through Tailscale SHALL be split by honk according to the rules, the same as LAN traffic. Traffic entering through WireGuard SHALL go direct, bypassing the proxy.

#### Scenario: Tailnet device reaches a proxied target
- **WHEN** a tailnet device uses this router as its exit node and accesses a target that the rules send through the proxy
- **THEN** the traffic leaves through the proxy node

#### Scenario: WireGuard device reaches the internet
- **WHEN** a WireGuard device accesses the internet through the router
- **THEN** the source address seen externally is the router's WAN address
