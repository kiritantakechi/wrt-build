# Spec Delta

## Purpose

Implement IPv4 full-cone NAT with einat on the PPPoE WAN interface; use a mark to accept only inbound connections that einat reverse-translated; fall back automatically to kernel masquerade when einat is unavailable.

## ADDED Requirements

### Requirement: Full-cone NAT44
IPv4 TCP, UDP, and ICMP traffic from the LAN SHALL be translated by einat, with both mapping and filtering independent of the external endpoint (EIM + EIF).

#### Scenario: Endpoint-independent mapping
- **WHEN** the same internal socket accesses two different external addresses in turn
- **THEN** both external addresses see the same public port

#### Scenario: Endpoint-independent filtering
- **WHEN** after the mapping is established, an external address that was never contacted sends a packet to that public port
- **THEN** the packet is delivered to the corresponding internal socket

### Requirement: Accept only einat-translated inbound connections
New connections forwarded from WAN to LAN SHALL be accepted only when the packet carries einat's reverse-translation mark. Any other new connection entering from WAN with an internal destination address MUST be dropped.

#### Scenario: Inbound packet with spoofed destination
- **WHEN** a neighbor host on the WAN side directly sends a new connection whose destination is an internal IP and which is unrelated to any mapping
- **THEN** the packet is dropped, and the internal host does not receive it

#### Scenario: Inbound packet to a mapped port
- **WHEN** an external host opens a new connection to a public port that has an established mapping
- **THEN** the connection is accepted and delivered to the corresponding internal host

### Requirement: Other protocols still use masquerade
IPv4 protocols other than TCP, UDP, and ICMP SHALL continue to be translated by kernel masquerade.

#### Scenario: IPsec ESP traffic
- **WHEN** a LAN client establishes an IPsec tunnel that uses ESP
- **THEN** ESP packets leave with the router's WAN address, and ESP packets sent back by the peer reach the client

### Requirement: Fall back to masquerade when einat stops
When einat stops running, TCP, UDP, and ICMP translation SHALL automatically fall back to kernel masquerade, and the LAN stays connected. At the same time, the rule that accepts inbound new connections by mark SHALL stop taking effect as well.

#### Scenario: Stop einat
- **WHEN** a LAN client accesses external networks after the einat service is stopped
- **THEN** access succeeds, translation is done by masquerade instead, and inbound new connections are no longer accepted

### Requirement: Port range isolated from local ports
The public port range that einat uses MUST NOT overlap the local ephemeral port range. Connections originated by the router itself MUST NOT have their ports rewritten by einat.

#### Scenario: Local connections not rewritten
- **WHEN** the router itself opens an outbound TCP connection
- **THEN** the source port seen externally is the local socket's port, not rewritten by einat

### Requirement: No IPv6 translation
einat MUST NOT perform any address translation on IPv6.

#### Scenario: LAN reaches external hosts over IPv6
- **WHEN** a LAN client accesses an external host over IPv6
- **THEN** the external host sees the client's own global IPv6 address as the source

### Requirement: Automatic recovery after redial
After a PPPoE redial, a re-created WAN interface, or a change of public address, einat SHALL re-attach within 60 seconds and restore full-cone behavior.

#### Scenario: Redial after PPPoE disconnect
- **WHEN** PPPoE disconnects and redials successfully
- **THEN** within 60 seconds, new connections again behave as full-cone NAT

### Requirement: Register a health check
einat SHALL register a check with the health check: the check passes only when the einat process is running and, if the WAN interface exists, einat is attached to it. A missing WAN interface (for example, before PPPoE has connected) MUST NOT cause the check to fail.

#### Scenario: PPPoE not yet connected
- **WHEN** the health check runs while einat is running but the pppoe-wan interface does not exist yet
- **THEN** the einat check passes
