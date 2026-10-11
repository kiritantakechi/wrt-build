# Spec Delta

## ADDED Requirements

### Requirement: Device code handles structured data in ucode
The device code of this project SHALL handle JSON, ubus and uci data in ucode: the files of the feed's packages, the image's own files, and the device side of config-push. It MUST NOT use jshn or jsonfilter, nor name `/etc/opkg`. Scripts whose callers expect a shell script stay POSIX sh: init scripts, uci-defaults and sysupgrade hooks.

#### Scenario: jsonfilter in a device script
- **WHEN** a device script of this project calls jsonfilter, sources jshn or names `/etc/opkg`
- **THEN** the check fails, and names the file and line
