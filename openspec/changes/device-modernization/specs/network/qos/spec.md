# Spec Delta

## MODIFIED Requirements

### Requirement: Shape upload only
With the image's configuration, egress on pppoe-wan SHALL be shaped by cake at the configured upload bandwidth, compensating for PPPoE encapsulation overhead. Ingress MUST NOT be shaped, and no ifb device SHALL exist: qosify learns DNS names without one.

#### Scenario: Inspect queueing disciplines
- **WHEN** the queueing disciplines of pppoe-wan and the network devices on the system are inspected
- **THEN** the root qdisc of pppoe-wan is cake running at the configured bandwidth, and there is no ifb device

### Requirement: DSCP classification
qosify SHALL classify egress traffic into the diffserv4 tins by rule (port, DNS name, bulk-flow detection).

#### Scenario: Classify into the voice tin
- **WHEN** a flow matches a rule set to the voice class
- **THEN** cake's statistics show that the flow entered the voice tin

#### Scenario: Classify by DNS name
- **WHEN** a rule sets a DNS name pattern to the voice class, a LAN host resolves a matching name through the router, and then sends a flow to the address it got
- **THEN** cake's statistics show that the flow entered the voice tin

## ADDED Requirements

### Requirement: Ingress shaping when configured
When qosify's configuration enables the ingress direction of an interface, qosify SHALL shape that interface's ingress with cake on an ifb device, to which its ingress classifier redirects the traffic. When the configuration no longer enables it, the ifb device SHALL go away.

#### Scenario: Enable ingress shaping
- **WHEN** ingress shaping is enabled for the WAN interface with a download bandwidth, a LAN host downloads, and the configuration is then restored
- **THEN** while it is enabled, cake on the interface's ifb counts the download's packets, and after the restore no ifb device remains
