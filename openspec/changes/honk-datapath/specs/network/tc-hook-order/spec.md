## RENAMED Requirements

- FROM: `### Requirement: Only dae on the LAN port`
- TO: `### Requirement: Only the proxy on the LAN port`

## MODIFIED Requirements

### Requirement: Only the proxy on the LAN port
On the LAN-side bound interfaces, honk SHALL be the only tc or tcx program.

#### Scenario: Check the LAN port
- **WHEN** all BPF programs attached to br-lan are inspected
- **THEN** only honk programs are present

### Requirement: Order independent of startup order
The order above SHALL hold under any startup order, after any component restart, and after a PPPoE redial.

#### Scenario: After restarting components
- **WHEN** qosify, einat, and honk are restarted in turn, and then PPPoE redials once
- **THEN** after each step, the programs and order on the WAN and LAN ports still meet the requirements above
