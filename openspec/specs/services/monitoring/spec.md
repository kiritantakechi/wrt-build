# services/monitoring Specification

## Purpose
Exports the router's runtime metrics in Prometheus format, exposed only on the LAN, for scraping by an external monitoring system.

## Requirements

### Requirement: Metrics exported on the LAN
The router SHALL serve metrics in Prometheus text format on port 9101 of its LAN address, covering at least CPU, memory, network interfaces, filesystems, and temperature. This port MUST NOT be reachable from the WAN.

#### Scenario: Scrape from the LAN
- **WHEN** a LAN host requests `http://10.0.0.1:9101/metrics`
- **THEN** Prometheus-format metrics are returned, including CPU, memory, network interfaces, and filesystems

#### Scenario: Temperature metrics
- **WHEN** metrics are requested from the LAN
- **THEN** the hwmon collector reports success, and the kernel has registered the Rockchip temperature sensor driver (`rockchip-thermal`), which exports the SoC temperature through hwmon on the board

#### Scenario: Access from the WAN
- **WHEN** the router's port 9101 is accessed from the WAN side
- **THEN** the connection is refused

### Requirement: Independent of the data disk
Metrics export SHALL keep working when the data disk is absent.

#### Scenario: No data disk attached
- **WHEN** metrics are requested from the LAN without the data disk attached
- **THEN** metrics are still returned, including data for the filesystem on the boot disk
