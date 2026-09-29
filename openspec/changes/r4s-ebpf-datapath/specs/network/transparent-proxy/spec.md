# Spec Delta

## Purpose

Use dae to provide rule-based transparent proxying for the LAN, containers, and overlay-network devices: direct traffic is forwarded entirely in the kernel, and router-originated traffic does not go through the proxy.

## ADDED Requirements

### Requirement: Bind LAN-side interfaces only
dae SHALL bind only br-lan, plus podman0 and tailscale0 when they exist. dae MUST NOT attach programs to any WAN interface, and MUST NOT attach cgroup hooks. A bound interface that appears after dae starts SHALL be bound within 60 seconds of appearing.

#### Scenario: Check programs on each interface
- **WHEN** dae is running and the BPF programs attached to br-lan and pppoe-wan are inspected
- **THEN** br-lan has dae programs, and pppoe-wan has no dae programs at all

#### Scenario: Container bridge appears after dae
- **WHEN** dae is already running and only then podman0 is created
- **THEN** within 60 seconds dae programs appear on podman0, and container traffic starts being split by rule

### Requirement: Rule-based traffic splitting
Traffic from bound interfaces SHALL be split by dae's rules:
- Direct traffic SHALL be forwarded directly by the kernel, without entering dae's user space;
- Proxied traffic SHALL leave through the configured proxy node.

#### Scenario: Access a direct target
- **WHEN** a LAN client accesses a target that the rules classify as direct
- **THEN** the connection succeeds, the target sees the router's WAN address as the source, and the router shows no connection from the dae process to that target

#### Scenario: Access a proxied target
- **WHEN** a LAN client accesses a target that the rules classify as proxied
- **THEN** the connection succeeds, and the target sees the proxy node's egress address as the source

### Requirement: Router-originated traffic goes direct
Traffic originated by the router's own processes MUST NOT be proxied through dae.

#### Scenario: Router accesses an external address
- **WHEN** a command on the router accesses an external address that the rules would otherwise classify as proxied
- **THEN** the target sees the router's WAN address as the source

### Requirement: Cover both IPv4 and IPv6
Splitting SHALL apply to both the IPv4 and the IPv6 traffic of the LAN.

#### Scenario: Access a proxied target over IPv6
- **WHEN** a LAN client accesses a target that the rules classify as proxied, over IPv6
- **THEN** the traffic leaves through the proxy node

### Requirement: Optional CPU pinning
dae SHALL be placed by the scheduler by default. An option SHALL pin it to the A72 cores (cpu4-5) instead.

#### Scenario: Enable CPU pinning
- **WHEN** the pinning option is enabled and dae restarts
- **THEN** dae runs only on cpu4-5, and its programs are on the bound interfaces again

### Requirement: Configuration management
dae's config SHALL be editable in LuCI and hot-reloaded on save. The full config (including subscriptions and node information) MUST NOT be preinstalled in the firmware image; its canonical copy lives in the private config repository.

#### Scenario: Save config in LuCI
- **WHEN** the dae config is modified and saved in LuCI
- **THEN** dae hot-reloads to apply it, and direct traffic is not interrupted during the reload

#### Scenario: Inspect the image
- **WHEN** the dae config in the firmware image is inspected
- **THEN** it contains only a template without subscriptions or node information

### Requirement: Fall back to direct when stopped
When dae stops or crashes, the dae programs on bound interfaces SHALL be removed, and LAN traffic SHALL fall back to direct forwarding by the kernel.

#### Scenario: Stop dae
- **WHEN** the dae service is stopped
- **THEN** LAN clients can still reach external networks, and all traffic goes direct

### Requirement: Register a health check
dae SHALL register a check with the health check: the check passes only when dae is running and its programs are attached to every bound interface that currently exists.

#### Scenario: dae not running
- **WHEN** the health check runs while the dae process is not running
- **THEN** the dae check fails
