# services/file-sharing Specification

## Purpose
Defines the exposure scope, share directories, and access control of the in-kernel SMB server (ksmbd), which provides file sharing on the LAN while using as little memory as possible.

## Requirements

### Requirement: LAN-only service
The SMB service SHALL be offered only on the LAN interface. It MUST NOT be reachable from the WAN, WireGuard, or Tailscale.

#### Scenario: Access from the LAN
- **WHEN** a LAN client connects to `smb://10.0.0.1`
- **THEN** the share list is visible

#### Scenario: Access from the WAN or VPN
- **WHEN** the router's port 445 is connected to from the WAN side, from a WireGuard device, and from a tailnet device in turn
- **THEN** the connection is refused in all three cases

### Requirement: Shares on the data disk
All shares SHALL point to directories under `@shares`. When the data disk is absent, the SMB service MUST NOT offer any shares.

#### Scenario: Data disk absent
- **WHEN** the system boots without the data disk
- **THEN** the SMB service is not running, and no shares are accessible

### Requirement: Authentication required
Access to shares SHALL require a username and password, and anonymous access MUST NOT be allowed. Credentials for share users MUST NOT be preset in the image.

#### Scenario: Anonymous access
- **WHEN** a client tries to connect to a share anonymously
- **THEN** the connection is refused

### Requirement: Protocol version
The SMB service SHALL offer only the SMB 3 protocol and MUST NOT accept SMB 1.

#### Scenario: Connect with an SMB 1 client
- **WHEN** a client that supports only SMB 1 tries to connect
- **THEN** negotiation fails
