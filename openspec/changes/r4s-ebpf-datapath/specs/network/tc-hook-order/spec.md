# Spec Delta

## Purpose

Define the attach order and return-value constraints for multiple eBPF/tc programs on the same interface, and how the packet mark bits used by each component are allocated, so the programs neither cut each other off nor conflict with each other.

## ADDED Requirements

### Requirement: Programs and order on the WAN port
On both ingress and egress of the WAN interface, einat SHALL be the first program to run, followed by qosify's filters. Components other than these two MUST NOT attach tc or tcx programs to the WAN interface.

#### Scenario: Check the WAN port
- **WHEN** all BPF programs attached to pppoe-wan are inspected
- **THEN** only einat is on tcx ingress and egress; the legacy tc filters are only qosify's, namely the BPF classifiers in both directions and the ingress filters that redirect DNS replies to `ifb-dns`

### Requirement: Pass-through returns continue the chain
When a program attached to a shared hook passes a packet, it MUST return "continue to the next program", not a terminating verdict. The only exception is when it intentionally drops or redirects the packet.

#### Scenario: ICMP reply on WAN ingress
- **WHEN** a LAN host pings an external address and the reply enters from WAN
- **THEN** the reply is first reverse-translated by einat to the internal address, then classified by qosify (qosify's ingress counters increase), and finally delivered to the host

#### Scenario: Fragmented UDP reply
- **WHEN** a LAN host receives a fragmented UDP reply that enters through WAN
- **THEN** all fragments are reverse-translated and delivered, and the application receives the complete data

### Requirement: Only dae on the LAN port
On the LAN-side bound interfaces, dae SHALL be the only tc or tcx program.

#### Scenario: Check the LAN port
- **WHEN** all BPF programs attached to br-lan are inspected
- **THEN** only dae programs are present

### Requirement: Order independent of startup order
The order above SHALL hold under any startup order, after any component restart, and after a PPPoE redial.

#### Scenario: After restarting components
- **WHEN** qosify, einat, and dae are restarted in turn, and then PPPoE redials once
- **THEN** after each step, the programs and order on the WAN and LAN ports still meet the requirements above

### Requirement: Centralized mark bit allocation
The packet mark bits used by each component SHALL be registered in a single allocation table in the repository, and the bits used by any two components MUST NOT overlap. The build check SHALL fail when the config contains an unregistered or overlapping mark.

#### Scenario: Overlapping mark configured
- **WHEN** a component's config uses a mark bit already registered by another component
- **THEN** the build check fails and reports the two conflicting components and the bit involved
