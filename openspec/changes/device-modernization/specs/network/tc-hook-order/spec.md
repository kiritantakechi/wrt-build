# Spec Delta

## MODIFIED Requirements

### Requirement: Programs and order on the WAN port
On both ingress and egress of the WAN interface, einat's program SHALL run first and qosify's classifier after it, both attached as tcx links. Components other than these two MUST NOT attach tc or tcx programs to the WAN interface, and no legacy tc filter SHALL be attached to it.

#### Scenario: Check the WAN port
- **WHEN** all BPF programs and tc filters attached to pppoe-wan are inspected
- **THEN** tcx ingress and egress each hold einat's program followed by qosify's classifier, and no legacy tc filter is attached
