# Spec Delta

## MODIFIED Requirements

### Requirement: Secrets stored encrypted
Secrets in the private config repository (PPPoE credentials, dae subscriptions and nodes, WireGuard private keys, the Tailscale auth key, SMB user credentials) SHALL be committed in encrypted form. Plaintext SHALL appear only temporarily, in memory or in a temporary directory on the workstation performing the push, and on the device. On the device, the files a push writes for a secret outside the uci configuration (its upload, dae's configuration, Tailscale's auth key) SHALL be readable by root alone, and no secret SHALL appear on a command line; the push's temporary files SHALL be gone once the push ends, however it ends.

#### Scenario: Scan the private repository
- **WHEN** the full history of the private config repository is checked with a secret scanner
- **THEN** no plaintext secrets are found

#### Scenario: Secrets on the device
- **WHEN** a push with a dae configuration, a Tailscale login and SMB users has ended, successfully or not
- **THEN** the push's temporary files were readable by root alone while they were there and are gone, dae's files and Tailscale's auth key are readable by root alone, and no process was started with the Tailscale auth key among its arguments

### Requirement: Roll back on service failure
After the configuration is written, if a service fails to reload, the push tool SHALL restore that service's pre-push configuration, reload it again, and then report the failure. The restored configuration SHALL include every file the push changed for that service, its login state among them, and every service the push reloads SHALL be checked for having come back, and staying back, including that no service that ran before the push stopped.

#### Scenario: Service reload fails
- **WHEN** the new configuration passes validation but the corresponding service fails to reload
- **THEN** the service is restored to its pre-push configuration and runs normally, and the push tool exits nonzero and states the reason

#### Scenario: Tailscale login fails
- **WHEN** Tailscale is logged in, and a push with a Tailscale login that the control server refuses is made
- **THEN** Tailscale is logged in again as before the push, and the push tool exits nonzero and states the reason

#### Scenario: A service that stops with its new configuration
- **WHEN** a push changes a configuration other than the network's, dae's or Tailscale's, and a service that ran before the push no longer runs once the configuration is applied
- **THEN** that configuration is restored, the service runs again, and the push tool exits nonzero and states the reason
