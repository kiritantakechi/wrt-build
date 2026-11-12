## ADDED Requirements

### Requirement: The proxy's state follows the data disk
honk SHALL keep its data directory (its state database, cached subscriptions and geodata) on the data disk while the data disk is mounted and writable, and in RAM otherwise, and never on the boot disk. The data disk's mount and unmount SHALL restart honk onto it and off it; honk SHALL proxy with or without the data disk.

#### Scenario: Boot without the data disk
- **WHEN** the router boots without the data disk, honk on
- **THEN** honk proxies with its state in RAM, and the boot disk holds nothing of it

#### Scenario: Data disk mounted and unmounted
- **WHEN** the data disk is mounted while honk runs, then unmounted, then mounted again
- **THEN** honk runs with its state on the data disk, then in RAM, then on the data disk again, and the boot disk holds nothing of it
