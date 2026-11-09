# Spec Delta

## MODIFIED Requirements

### Requirement: Bind LAN-side interfaces only
dae SHALL bind only br-lan, plus podman0 and tailscale0 when they exist. dae MUST NOT attach programs to any WAN interface, and MUST NOT attach cgroup hooks. A bound interface that appears after dae starts SHALL be bound within 60 seconds of appearing, also while dae is still starting or reloading.

#### Scenario: Check programs on each interface
- **WHEN** dae is running and the BPF programs attached to br-lan and pppoe-wan are inspected
- **THEN** br-lan has dae programs, and pppoe-wan has no dae programs at all

#### Scenario: Container bridge appears after dae
- **WHEN** dae is already running and only then podman0 is created
- **THEN** within 60 seconds dae programs appear on podman0, and container traffic starts being split by rule

#### Scenario: Container bridge appears while dae starts
- **WHEN** podman0 is created right after dae was started anew, before dae is ready
- **THEN** within 60 seconds dae programs appear on podman0

### Requirement: Configuration management
dae's config SHALL be editable in LuCI and hot-reloaded on save. The full config (including subscriptions and node information) MUST NOT be preinstalled in the firmware image; its canonical copy lives in the private config repository. Turning dae off in its configuration SHALL stop it when the configuration is applied.

#### Scenario: Save config in LuCI
- **WHEN** the dae config is modified and saved in LuCI
- **THEN** dae hot-reloads to apply it, and direct traffic is not interrupted during the reload

#### Scenario: Inspect the image
- **WHEN** the dae config in the firmware image is inspected
- **THEN** it contains only a template without subscriptions or node information

#### Scenario: Turn dae off
- **WHEN** dae runs, its `enabled` option is set to 0, and the configuration is applied
- **THEN** dae stops, and no dae programs remain on the bound interfaces
