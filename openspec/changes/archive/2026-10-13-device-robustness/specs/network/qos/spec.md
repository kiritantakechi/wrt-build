# Spec Delta

## MODIFIED Requirements

### Requirement: Ingress shaping when configured
When qosify's configuration enables the ingress direction of an interface, qosify SHALL shape that interface's ingress with cake on an ifb device, to which its ingress classifier redirects the traffic. The ifb device's name SHALL be derived from the device name of the interface alone, SHALL fit the kernel's limit on interface names whatever that device name's length, and SHALL be what qosify's status reports for the interface. When the configuration no longer enables it, the ifb device SHALL go away.

#### Scenario: Enable ingress shaping
- **WHEN** ingress shaping is enabled for the WAN interface with a download bandwidth, a LAN host downloads, and the configuration is then restored
- **THEN** while it is enabled, cake on the interface's ifb counts the download's packets, and after the restore no ifb device remains

#### Scenario: Ingress shaping on a device with a long name
- **WHEN** ingress shaping is enabled for a device whose name is 14 characters long, and its configuration is then removed
- **THEN** qosify's status names the device's ifb, an ifb of that name exists with cake on it, its name begins with the device name's first two characters and ends with its last nine, and after the removal no ifb device remains
