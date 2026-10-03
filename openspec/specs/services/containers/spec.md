# services/containers Specification

## Purpose
Defines where the container runtime stores data, how networking and firewalling are divided, how container traffic relates to the transparent proxy, and how declaratively defined app containers start automatically on boot.

## Requirements

### Requirement: Container storage on the data disk
Container images and container data SHALL all be stored on `@containers`. The boot disk MUST NOT hold any container image layers or container data.

#### Scenario: Pull an image
- **WHEN** a container image is pulled
- **THEN** the image layers are written to `@containers`, and usage of the overlay partition does not increase

### Requirement: Single firewall and single NAT
The container runtime MUST NOT install its own firewall or NAT rules. The container bridge SHALL belong to a dedicated zone in fw4, and outbound address translation for containers SHALL be done by einat, as for the LAN (falling back to masquerade when einat is unavailable). Exposing a container port externally SHALL be done with fw4 port forward rules.

#### Scenario: Check the ruleset
- **WHEN** a bridged container is run and the nftables ruleset is inspected
- **THEN** it contains no tables created by the container runtime, only rules from fw4 and the datapath components

#### Scenario: Container reaches the internet
- **WHEN** a bridged container accesses the internet
- **THEN** the access succeeds, and the source address seen externally is the router's WAN address

#### Scenario: Expose a container port
- **WHEN** a WAN port forward to a container is configured in fw4, with a port outside einat's port range
- **THEN** the container port is reachable from outside

### Requirement: Container traffic uses the transparent proxy
Traffic on the container bridge SHALL be split by dae according to the rules, the same as LAN traffic.

#### Scenario: Container reaches a proxied target
- **WHEN** a container accesses a target that the rules send through the proxy
- **THEN** the traffic leaves through the proxy node

### Requirement: Declarative definition and autostart on boot
App containers SHALL be defined by declaration files stored on the data disk. After the data disk is mounted, the system SHALL start the corresponding containers automatically from these declaration files, with consistent results on repeated runs (no rebuild when the declaration is unchanged).

#### Scenario: Start on boot
- **WHEN** the data disk holds a declaration file for an app container (for example, qBittorrent) and the system reboots
- **THEN** the container runs automatically once the data disk is mounted

#### Scenario: Declaration unchanged
- **WHEN** the declaration file is unchanged and the startup flow is triggered again
- **THEN** the running container is not rebuilt

### Requirement: App containers stay out of the firmware
Apps such as qBittorrent SHALL run as containers, and the firmware image MUST NOT include their native packages.

#### Scenario: Check the image
- **WHEN** the packages in the firmware image are listed
- **THEN** the list contains no qBittorrent, Qt, or libtorrent
