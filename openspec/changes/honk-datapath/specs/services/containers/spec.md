## MODIFIED Requirements

### Requirement: Container traffic uses the transparent proxy
Traffic on the container bridge SHALL be split by honk according to the rules, the same as LAN traffic.

#### Scenario: Container reaches a proxied target
- **WHEN** a container accesses a target that the rules send through the proxy
- **THEN** the traffic leaves through the proxy node
