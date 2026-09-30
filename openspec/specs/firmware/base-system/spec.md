# firmware/base-system Specification

## Purpose
Define the firmware's factory defaults and basic user experience: management address, web management interface, interface language, interactive shell, memory compression, and password policy, plus the components that are explicitly excluded.

## Requirements

### Requirement: Default LAN address
Without preserved configuration, the default LAN address SHALL be 10.0.0.1/24, and the address in failsafe mode SHALL also be 10.0.0.1. A config-preserving upgrade MUST NOT overwrite a LAN address the user has set.

#### Scenario: Fresh install
- **WHEN** the router boots for the first time after flashing, with no preserved configuration
- **THEN** the address of br-lan is 10.0.0.1/24

#### Scenario: Enter failsafe mode
- **WHEN** the router enters failsafe mode
- **THEN** the router is reachable at 10.0.0.1

#### Scenario: Config-preserving upgrade
- **WHEN** the user changes the LAN address to a different address and then performs a config-preserving upgrade
- **THEN** after the upgrade, the LAN address is still the one the user set

### Requirement: Web management interface
LuCI SHALL be served by uhttpd with ucode and ship the Simplified Chinese language pack; the interface language SHALL stay at LuCI's default `auto` and follow the browser's language setting. The image MUST NOT contain nginx or uwsgi.

#### Scenario: Open the management interface
- **WHEN** a browser whose language is set to Simplified Chinese opens `http://10.0.0.1` on the LAN
- **THEN** uhttpd returns the LuCI page, and the interface language is Simplified Chinese

#### Scenario: No nginx or uwsgi
- **WHEN** the packages installed in the image are listed
- **THEN** neither nginx nor uwsgi is among them

### Requirement: Interactive shell
The root login shell SHALL be `/bin/ash`. An interactive login session SHALL switch to zsh automatically when zsh is available, loading the autosuggestions and syntax-highlighting plugins; when zsh is unavailable, it MUST stay in ash. Non-interactive command execution MUST NOT start zsh. The image SHALL also provide bash, which the user can enter manually; bash started as a login shell MUST NOT be switched to zsh.

#### Scenario: Interactive SSH login
- **WHEN** root logs in interactively over SSH
- **THEN** a zsh session starts with both plugins loaded

#### Scenario: Non-interactive command
- **WHEN** a command is run remotely over SSH without allocating a terminal
- **THEN** ash runs the command, and zsh is not started

#### Scenario: zsh unavailable
- **WHEN** the zsh executable does not exist or cannot be executed
- **THEN** the interactive login still succeeds and stays in ash

#### Scenario: Enter bash manually
- **WHEN** `bash -l` is run after login
- **THEN** a bash session starts and is not switched to zsh

### Requirement: Compressed memory swap
The system SHALL provide a 1 GiB zram swap device compressed with zstd.

#### Scenario: Check swap device
- **WHEN** the swap devices are inspected after boot completes
- **THEN** there is a 1 GiB zram swap device whose compression algorithm is zstd

### Requirement: No preset password
The image MUST NOT contain any preset root password hash. The administrator SHALL set the password on first use.

#### Scenario: Check shadow file
- **WHEN** `/etc/shadow` in the image is inspected
- **THEN** the root entry has no password hash

### Requirement: Excluded components
The image MUST NOT contain the following components: UPX-compressed executables, LRNG, urngd, shortcut-fe, natflow, the PCRE1 library, opkg.

#### Scenario: Check installed packages and executables
- **WHEN** the packages in the image are listed and its executables are scanned
- **THEN** none of the components above are present, and no executable carries a UPX marker
