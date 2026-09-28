# Spec Delta

## Purpose

Define WAN-side behavior: PPPoE dial-up, TCP MSS clamping, IPv6 prefix delegation and firewalling, and software forwarding acceleration.

## ADDED Requirements

### Requirement: PPPoE dial-up
WAN SHALL dial PPPoE over eth0. Dial-up credentials SHALL be provided at runtime and MUST NOT be preinstalled in the firmware image.

#### Scenario: Image contains no credentials
- **WHEN** the network config in the firmware image is inspected
- **THEN** WAN is of type PPPoE, and the username and password are both empty

#### Scenario: Dial after pushing credentials
- **WHEN** dial-up credentials are pushed to the device
- **THEN** the pppoe-wan interface comes up and gets an IPv4 address assigned by the ISP

### Requirement: MSS clamping
For TCP connections forwarded through WAN, the MSS in SYN packets SHALL be clamped to a value that matches the path MTU.

#### Scenario: LAN host opens a TCP connection
- **WHEN** a LAN host opens a TCP connection through WAN
- **THEN** the MSS that the peer receives is at most 1452

### Requirement: IPv6 prefix delegation
The router SHALL obtain an IPv6 prefix through DHCPv6-PD over PPPoE and assign it to the LAN through RA and DHCPv6. LAN hosts SHALL get global IPv6 addresses and MUST NOT go through NAT66.

#### Scenario: LAN host gets IPv6
- **WHEN** a LAN host joins the network
- **THEN** it gets a global IPv6 address within the prefix and can reach the IPv6 internet

### Requirement: IPv6 inbound firewall
New IPv6 connections from WAN into LAN SHALL be rejected by default, except where a rule explicitly allows them.

#### Scenario: External host connects to an internal IPv6 address
- **WHEN** an external host initiates a TCP connection to a LAN host's global IPv6 address
- **THEN** the connection is rejected

### Requirement: Software acceleration does not bypass NAT
The software flowtable SHALL be enabled. Accelerated flows MUST still go through einat's address translation.

#### Scenario: Check acceleration and source address while downloading
- **WHEN** a LAN host is downloading continuously, and the flowtable acceleration and the source address seen externally are inspected
- **THEN** the flow is accelerated, and the source address seen externally is always the router's WAN address
