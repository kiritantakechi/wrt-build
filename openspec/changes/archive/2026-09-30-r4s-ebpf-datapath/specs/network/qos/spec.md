# Spec Delta

## Purpose

Shape the upload direction of the PPPoE WAN interface with cake and classify by DSCP; do not shape the download direction, so flowtable forwarding acceleration is preserved.

## ADDED Requirements

### Requirement: Shape upload only
Egress on pppoe-wan SHALL be shaped by cake at the configured upload bandwidth, compensating for PPPoE encapsulation overhead. Ingress MUST NOT be shaped, and an ifb device MUST NOT be created for ingress shaping. The `ifb-dns` that qosify creates for classification by DNS name does no shaping and is exempt from this restriction.

#### Scenario: Inspect queueing disciplines
- **WHEN** the queueing disciplines of pppoe-wan and the network devices on the system are inspected
- **THEN** the root qdisc of pppoe-wan is cake running at the configured bandwidth; the only ifb device on the system is `ifb-dns`, and it has no cake

### Requirement: Fair sharing across internal hosts
Even though address translation is done by einat, cake SHALL still share upload bandwidth fairly among LAN hosts.

#### Scenario: Two hosts upload at full speed
- **WHEN** two LAN hosts upload at the same time as fast as they can, for 60 seconds
- **THEN** their average upload rates differ by no more than 20%

### Requirement: DSCP classification
qosify SHALL classify egress traffic into the diffserv4 tins by rule (port, DNS name, bulk-flow detection).

#### Scenario: Classify into the voice tin
- **WHEN** a flow matches a rule set to the voice class
- **THEN** cake's statistics show that the flow entered the voice tin

### Requirement: Recovery after redial
After a PPPoE redial or a re-created WAN interface, shaping and classification SHALL recover within 60 seconds.

#### Scenario: PPPoE redial
- **WHEN** PPPoE disconnects and then redials successfully
- **THEN** within 60 seconds, cake and the qosify classifier reappear on pppoe-wan
