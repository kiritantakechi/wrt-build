# Spec Delta

## MODIFIED Requirements

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
