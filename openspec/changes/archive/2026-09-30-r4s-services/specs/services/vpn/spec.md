# Spec Delta

## Purpose

Defines the roles of the two networking options, WireGuard and Tailscale, their placement in the firewall, and their relation to the transparent proxy.

## ADDED Requirements

### Requirement: WireGuard remote access
The firmware SHALL provide in-kernel WireGuard so that remote devices can connect home and access the LAN. The WireGuard private key and peer configuration MUST NOT be preset in the image.

#### Scenario: Remote device connects
- **WHEN** a configured remote device connects to the router over WireGuard
- **THEN** it can reach hosts on the LAN, but cannot reach router services that are open only to the LAN (such as SMB)

### Requirement: Tailscale networking
The firmware SHALL provide Tailscale and SHALL be able to advertise the LAN subnet as a subnet route. Tailscale's firewall rules SHALL use nftables. Authentication credentials MUST NOT be preset in the image.

#### Scenario: Reach the LAN via subnet route
- **WHEN** another device in the tailnet accesses a host on the LAN
- **THEN** the access succeeds through this router's subnet route

### Requirement: Relation to the transparent proxy
Traffic entering through Tailscale SHALL be split by dae according to the rules, the same as LAN traffic. Traffic entering through WireGuard SHALL go direct, bypassing the proxy.

#### Scenario: Tailnet device reaches a proxied target
- **WHEN** a tailnet device uses this router as its exit node and accesses a target that the rules send through the proxy
- **THEN** the traffic leaves through the proxy node

#### Scenario: WireGuard device reaches the internet
- **WHEN** a WireGuard device accesses the internet through the router
- **THEN** the source address seen externally is the router's WAN address

### Requirement: Mark bit registration
The packet mark bits that Tailscale uses SHALL be registered in the mark allocation table and MUST NOT overlap with those of other components.

#### Scenario: Check the allocation table
- **WHEN** the mark check runs
- **THEN** the allocation table contains a Tailscale entry, and the check passes
