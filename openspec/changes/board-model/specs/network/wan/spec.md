# Spec Delta

## MODIFIED Requirements

### Requirement: PPPoE dial-up
WAN SHALL dial PPPoE over the board's WAN port, as upstream's board configuration assigns it: eth0 on the NanoPi R4S, eth1 on the NanoPi R6S. Dial-up credentials SHALL be provided at runtime and MUST NOT be preinstalled in the firmware image. The image's network defaults SHALL apply to a fresh configuration only; a configuration carried over by an upgrade MUST keep its values.

#### Scenario: Image contains no credentials
- **WHEN** the network config in the firmware image is inspected
- **THEN** WAN is of type PPPoE on the board's WAN port, and the username and password are both empty

#### Scenario: Upgrade keeps the pushed configuration
- **WHEN** credentials have been pushed and network defaults changed, and a config-preserving upgrade is performed
- **THEN** after the upgrade, the credentials and the changed values are unchanged

#### Scenario: Dial after pushing credentials
- **WHEN** dial-up credentials are pushed to the device
- **THEN** the pppoe-wan interface comes up and gets an IPv4 address assigned by the ISP
