## MODIFIED Requirements

### Requirement: Container traffic uses the transparent proxy
Traffic on the container bridge SHALL be split by honk according to the rules, the same as LAN traffic. honk SHALL leave the containers' network namespaces where podman registered them.

#### Scenario: Container reaches a proxied target
- **WHEN** a container accesses a target that the rules send through the proxy
- **THEN** the traffic leaves through the proxy node

#### Scenario: honk restarts beside the Pods
- **WHEN** honk restarts while the Pods run, with a Pod's network namespace registered before honk started or while it ran
- **THEN** the namespace stays where podman registered it
