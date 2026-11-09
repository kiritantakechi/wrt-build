# services/containers Specification

## Purpose
Defines where the container runtime stores data, how networking and firewalling are divided, how container traffic relates to the transparent proxy, and how declaratively defined app containers start automatically on boot.

## Requirements

### Requirement: Container storage on the data disk
Container images and container data SHALL all be stored on `@containers`. The boot disk MUST NOT hold any container image layers or container data. Container runtime commands that start at the same time SHALL all accept the storage configuration that the runtime recorded on `@containers`, however their start interleaves with the creation of the runtime's working directories. Once they have ended, nothing they mounted SHALL stay mounted under `@containers`, however their work interleaves with one another's.

#### Scenario: Pull an image
- **WHEN** a container image is pulled
- **THEN** the image layers are written to `@containers`, and usage of the overlay partition does not increase

#### Scenario: Runtime commands at the same time
- **WHEN** several container runtime commands start at once, repeatedly, each time with the runtime's working directories in RAM not yet created, as after a boot
- **THEN** every command succeeds, none reports a mismatch with the recorded storage configuration, and nothing stays mounted under `@containers` once they have all ended

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
App containers SHALL be defined by declaration files stored on the data disk. After the data disk is mounted, the system SHALL start the corresponding containers automatically from these declaration files, with consistent results on repeated runs (no rebuild when the declaration is unchanged). A declaration whose container cannot be started MUST NOT keep the others from starting; the start SHALL report each that failed. A container SHALL stop and start again, its network's DNS answering it, also after a service that ran a container of its own has ended.

#### Scenario: Start on boot
- **WHEN** the data disk holds a declaration file for an app container (for example, qBittorrent) and the system reboots
- **THEN** the container runs automatically once the data disk is mounted

#### Scenario: Declaration unchanged
- **WHEN** the declaration file is unchanged and the startup flow is triggered again
- **THEN** the running container is not rebuilt

#### Scenario: A declaration that cannot start
- **WHEN** the data disk holds two declarations, and the one that comes first by name names an image that cannot be had, and the startup flow runs
- **THEN** the other container runs, and the startup flow fails, naming the declaration that did not start

#### Scenario: A service's container ended
- **WHEN** a service ran a container on podman's network and ended with it, as the release sync does, and the app container is then stopped and started again
- **THEN** both succeed, and the network's DNS answers the app container

### Requirement: App containers stay out of the firmware
Apps such as qBittorrent SHALL run as containers, and the firmware image MUST NOT include their native packages.

#### Scenario: Check the image
- **WHEN** the packages in the firmware image are listed
- **THEN** the list contains no qBittorrent, Qt, or libtorrent
