# Spec Delta

## MODIFIED Requirements

### Requirement: Image and kmods from the same build
Each build SHALL output a manifest that records at least: the board it was built for and the board's OpenWrt device, the build run identifier, the hash of `upstream.lock`, the kernel version identifier (vermagic), and the checksums of the image and the package index. The image and the package repository MUST be handed to the downstream release process as a single unit.

#### Scenario: Complete manifest
- **WHEN** a build finishes successfully
- **THEN** the artifacts include this manifest, it names the board that was built and its device, and the vermagic it records matches the image kernel and the kmods in the repository
