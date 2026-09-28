# Spec Delta

## Purpose

Defines how runtime configuration and secrets are stored, and how they are pushed to the device and applied: secrets are kept encrypted in a private repository, configuration is validated before a push, a failure rolls back, and configuration persists across A/B upgrades.

## ADDED Requirements

### Requirement: Secrets stored encrypted
Secrets in the private config repository (PPPoE credentials, dae subscriptions and nodes, WireGuard private keys, the Tailscale auth key, SMB user credentials) SHALL be committed in encrypted form. Plaintext SHALL appear only temporarily, in memory or in a temporary directory on the workstation performing the push, and on the device.

#### Scenario: Scan the private repository
- **WHEN** the full history of the private config repository is checked with a secret scanner
- **THEN** no plaintext secrets are found

### Requirement: Validate before pushing
The push tool SHALL validate all configuration to be pushed, including the dae configuration syntax and the UCI configuration syntax, before it modifies the device. When validation fails, the device MUST NOT be changed in any way.

#### Scenario: Syntax error in dae config
- **WHEN** a dae configuration with a syntax error is pushed
- **THEN** the push aborts before modifying the device, and the device's existing configuration and services remain unchanged

### Requirement: Repeatable push results
Pushing the same configuration repeatedly SHALL produce the same result, and MUST NOT restart services whose configuration has not changed.

#### Scenario: Repeated push
- **WHEN** the same configuration is pushed twice in a row
- **THEN** the second push restarts no services

### Requirement: Roll back on service failure
After the configuration is written, if a service fails to reload, the push tool SHALL restore that service's pre-push configuration, reload it again, and then report the failure.

#### Scenario: Service reload fails
- **WHEN** the new configuration passes validation but the corresponding service fails to reload
- **THEN** the service is restored to its pre-push configuration and runs normally, and the push tool exits nonzero and states the reason

### Requirement: Configuration persists across A/B upgrades
Configuration and secrets pushed to the device SHALL be included in the configuration backup taken during an upgrade, and SHALL still be present after the slot switch.

#### Scenario: Upgrade to the other slot
- **WHEN** a config-preserving upgrade is performed after a configuration push
- **THEN** the PPPoE, dae, WireGuard, Tailscale, and SMB configuration is all still present in the new slot

### Requirement: dae user config cannot set bind interfaces
The push tool MUST reject dae user configuration that contains `lan_interface` or `wan_interface`, because the firmware generates these two settings automatically.

#### Scenario: User config sets lan_interface
- **WHEN** a dae configuration whose user config sets `lan_interface` is pushed
- **THEN** the push fails during validation and reports that this field is managed by the firmware

### Requirement: SSH key authentication only
Pushes SHALL connect to the device with SSH key authentication and MUST NOT use password authentication.

#### Scenario: No SSH key configured
- **WHEN** a push is attempted while the push public key is not deployed on the device
- **THEN** the push aborts on the authentication failure and does not fall back to password login
