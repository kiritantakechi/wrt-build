# Spec Delta

## MODIFIED Requirements

### Requirement: Programs and order on the WAN port
On both ingress and egress of the WAN interface, einat's program SHALL run first and qosify's classifier after it, both attached as tcx links. Components other than these two MUST NOT attach tc or tcx programs to the WAN interface, and no legacy tc filter SHALL be attached to it. On a kernel that refuses tcx links, qosify SHALL attach its classifiers with `clsact` instead, still after einat's program.

#### Scenario: Check the WAN port
- **WHEN** all BPF programs and tc filters attached to pppoe-wan are inspected
- **THEN** tcx ingress and egress each hold einat's program followed by qosify's classifier, and no legacy tc filter is attached

#### Scenario: Kernel without tcx
- **WHEN** qosify cannot use tcx links (`qosify.global.tcx=off` stands in for such a kernel) and the WAN port is inspected
- **THEN** each direction runs einat's tcx program first and qosify's classifier on `clsact` after it, and qosify still classifies traffic
