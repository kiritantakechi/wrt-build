# Spec Delta

## MODIFIED Requirements

### Requirement: Container storage on the data disk
Container images and container data SHALL all be stored on `@containers`. The boot disk MUST NOT hold any container image layers or container data.

#### Scenario: Pull an image
- **WHEN** a container image is pulled
- **THEN** the image layers are written to `@containers`, and usage of the overlay partition does not increase
