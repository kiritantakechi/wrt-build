# Spec Delta

## MODIFIED Requirements

### Requirement: Excluded components
The image MUST NOT contain the following components: UPX-compressed executables, LRNG, urngd, shortcut-fe, natflow, the PCRE1 library, opkg, nor any `/etc/opkg` directory.

#### Scenario: Check installed packages and executables
- **WHEN** the packages in the image are listed and its executables are scanned
- **THEN** none of the components above are present, no executable carries a UPX marker, and there is no `/etc/opkg`
