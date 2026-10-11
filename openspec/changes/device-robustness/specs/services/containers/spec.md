# Spec Delta

## MODIFIED Requirements

### Requirement: Container storage on the data disk
Container images and container data SHALL all be stored on `@containers`. The boot disk MUST NOT hold any container image layers or container data. Container runtime commands that start at the same time SHALL all accept the storage configuration that the runtime recorded on `@containers`, however their start interleaves with the creation of the runtime's working directories.

#### Scenario: Pull an image
- **WHEN** a container image is pulled
- **THEN** the image layers are written to `@containers`, and usage of the overlay partition does not increase

#### Scenario: Runtime commands at the same time
- **WHEN** several container runtime commands start at once, repeatedly, each time with the runtime's working directories in RAM not yet created, as after a boot
- **THEN** every command succeeds, and none reports a mismatch with the recorded storage configuration
